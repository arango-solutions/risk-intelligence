import os
from dotenv import load_dotenv
from arango import ArangoClient
from datetime import datetime

# Load environment variables
load_dotenv()

ARANGO_ENDPOINT = os.getenv("ARANGO_ENDPOINT")
ARANGO_USERNAME = os.getenv("ARANGO_USERNAME", "root")
ARANGO_PASSWORD = os.getenv("ARANGO_PASSWORD")
ARANGO_DATABASE = os.getenv("ARANGO_DATABASE", "risk-management")

def fix_analytics_viewpoint_links():
    """Ensure analytics actions are linked to both Default viewpoints."""
    client = ArangoClient(hosts=ARANGO_ENDPOINT)
    db = client.db(ARANGO_DATABASE, username=ARANGO_USERNAME, password=ARANGO_PASSWORD)
    
    print(f"\n{'='*80}")
    print("FIXING ANALYTICS ACTIONS VIEWPOINT LINKS")
    print(f"{'='*80}\n")
    
    canvas_col = db.collection("_canvasActions")
    vp_col = db.collection("_viewpoints")
    vp_act_col = db.collection("_viewpointActions")
    
    graphs = ["DataGraph", "KnowledgeGraph"]
    
    for graph_id in graphs:
        print(f"\n{'='*80}")
        print(f"PROCESSING {graph_id}")
        print(f"{'='*80}\n")
        
        # Get both viewpoints
        default_vp = list(vp_col.find({"graphId": graph_id, "name": "Default"}))
        default_graph_vp = list(vp_col.find({"graphId": graph_id, "name": f"Default - {graph_id}"}))
        
        if not default_vp:
            print(f"⚠️  No 'Default' viewpoint found")
            continue
        if not default_graph_vp:
            print(f"⚠️  No 'Default - {graph_id}' viewpoint found")
            continue
        
        default_vp_id = default_vp[0]["_id"]
        default_graph_vp_id = default_graph_vp[0]["_id"]
        
        print(f"Using viewpoints:")
        print(f"  - Default (_id: {default_vp_id})")
        print(f"  - Default - {graph_id} (_id: {default_graph_vp_id})")
        
        # Get analytics actions
        analytics_actions = list(canvas_col.find({
            "graphId": graph_id,
            "name": {"$like": "%Trace to Sanctioned%"}
        }))
        
        print(f"\nFound {len(analytics_actions)} analytics action(s)\n")
        
        now = datetime.utcnow().isoformat() + "Z"
        
        for action in analytics_actions:
            action_name = action.get("name")
            action_id = action["_id"]
            
            print(f"Fixing: {action_name}")
            
            # Check existing links
            existing_links = list(vp_act_col.find({"_to": action_id}))
            linked_viewpoints = {link.get("_from") for link in existing_links}
            
            # Add link to Default - GraphName if missing
            if default_graph_vp_id not in linked_viewpoints:
                vp_act_col.insert({
                    "_from": default_graph_vp_id,
                    "_to": action_id,
                    "createdAt": now,
                    "updatedAt": now
                })
                print(f"  ✓ Added link to 'Default - {graph_id}'")
            else:
                print(f"  ✓ Already linked to 'Default - {graph_id}'")
            
            # Ensure link to Default exists
            if default_vp_id not in linked_viewpoints:
                vp_act_col.insert({
                    "_from": default_vp_id,
                    "_to": action_id,
                    "createdAt": now,
                    "updatedAt": now
                })
                print(f"  ✓ Added link to 'Default'")
            else:
                print(f"  ✓ Already linked to 'Default'")
    
    print(f"\n{'='*80}")
    print("FIX COMPLETE")
    print(f"{'='*80}\n")

if __name__ == "__main__":
    fix_analytics_viewpoint_links()
