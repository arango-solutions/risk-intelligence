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

def fix_viewpoint_links():
    """Ensure all actions are linked to the 'Default' viewpoint (not 'Default - GraphName')."""
    client = ArangoClient(hosts=ARANGO_ENDPOINT)
    db = client.db(ARANGO_DATABASE, username=ARANGO_USERNAME, password=ARANGO_PASSWORD)
    
    print(f"\n{'='*80}")
    print("FIXING VIEWPOINT LINKS")
    print(f"{'='*80}\n")
    
    canvas_col = db.collection("_canvasActions")
    vp_col = db.collection("_viewpoints")
    vp_act_col = db.collection("_viewpointActions")
    
    graphs = ["OntologyGraph", "DataGraph", "KnowledgeGraph"]
    
    for graph_id in graphs:
        print(f"\n{'='*80}")
        print(f"GRAPH: {graph_id}")
        print(f"{'='*80}\n")
        
        # Find the "Default" viewpoint (not "Default - GraphName")
        default_vp = list(vp_col.find({"graphId": graph_id, "name": "Default"}))
        
        if not default_vp:
            print(f"⚠️  No 'Default' viewpoint found for {graph_id}")
            continue
        
        default_vp = default_vp[0]
        print(f"Using viewpoint: {default_vp.get('name')} (_id: {default_vp.get('_id')})")
        
        # Get all custom actions for this graph
        all_actions = list(canvas_col.find({"graphId": graph_id}))
        custom_actions = [a for a in all_actions if "2-hop neighbors" not in a.get("name", "") and "default" not in a.get("name", "").lower()]
        
        print(f"\nEnsuring {len(custom_actions)} action(s) are linked to 'Default' viewpoint:")
        
        now = datetime.utcnow().isoformat() + "Z"
        linked_count = 0
        new_links = 0
        
        for action in custom_actions:
            action_id = action["_id"]
            action_name = action.get("name")
            
            # Check if already linked to Default viewpoint
            existing_link = list(vp_act_col.find({
                "_from": default_vp["_id"],
                "_to": action_id
            }))
            
            if existing_link:
                print(f"  ✓ {action_name}: already linked")
                linked_count += 1
            else:
                # Check if linked to other viewpoints
                other_links = list(vp_act_col.find({"_to": action_id}))
                if other_links:
                    print(f"  ⚠️  {action_name}: linked to other viewpoint(s), adding link to 'Default'")
                else:
                    print(f"  ❌ {action_name}: not linked, adding link to 'Default'")
                
                # Add link to Default viewpoint
                vp_act_col.insert({
                    "_from": default_vp["_id"],
                    "_to": action_id,
                    "createdAt": now,
                    "updatedAt": now
                })
                new_links += 1
                linked_count += 1
        
        print(f"\n  Summary: {linked_count}/{len(custom_actions)} actions linked to 'Default' viewpoint")
        if new_links > 0:
            print(f"  → Added {new_links} new link(s)")

if __name__ == "__main__":
    fix_viewpoint_links()
