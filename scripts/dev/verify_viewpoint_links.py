import os
from dotenv import load_dotenv
from arango import ArangoClient

# Load environment variables
load_dotenv()

ARANGO_ENDPOINT = os.getenv("ARANGO_ENDPOINT")
ARANGO_USERNAME = os.getenv("ARANGO_USERNAME", "root")
ARANGO_PASSWORD = os.getenv("ARANGO_PASSWORD")
ARANGO_DATABASE = os.getenv("ARANGO_DATABASE", "risk-management")

def verify_viewpoint_links():
    """Verify that all canvas actions are properly linked to viewpoints."""
    client = ArangoClient(hosts=ARANGO_ENDPOINT)
    db = client.db(ARANGO_DATABASE, username=ARANGO_USERNAME, password=ARANGO_PASSWORD)
    
    print(f"\n{'='*80}")
    print("VERIFYING VIEWPOINT LINKS FOR CANVAS ACTIONS")
    print(f"{'='*80}\n")
    
    if not db.has_collection("_canvasActions") or not db.has_collection("_viewpoints") or not db.has_collection("_viewpointActions"):
        print("❌ Required collections missing")
        return
    
    canvas_col = db.collection("_canvasActions")
    vp_col = db.collection("_viewpoints")
    vp_act_col = db.collection("_viewpointActions")
    
    # Get all graphs
    graphs = ["OntologyGraph", "DataGraph", "KnowledgeGraph"]
    
    for graph_id in graphs:
        print(f"\n{'='*80}")
        print(f"GRAPH: {graph_id}")
        print(f"{'='*80}\n")
        
        # Get viewpoints for this graph
        viewpoints = list(vp_col.find({"graphId": graph_id}))
        print(f"Viewpoints: {len(viewpoints)}")
        for vp in viewpoints:
            print(f"  - {vp.get('name')} (_id: {vp.get('_id')})")
        
        # Get actions for this graph (excluding default)
        actions = list(canvas_col.find({"graphId": graph_id}))
        custom_actions = [a for a in actions if "2-hop neighbors" not in a.get("name", "") and "default" not in a.get("name", "").lower()]
        
        print(f"\nCustom actions: {len(custom_actions)}")
        for action in custom_actions:
            print(f"  - {action.get('name')} (_id: {action.get('_id')})")
        
        # Check links
        print(f"\nChecking viewpoint links:")
        unlinked_actions = []
        
        for action in custom_actions:
            action_id = action["_id"]
            links = list(vp_act_col.find({"_to": action_id}))
            
            if links:
                print(f"  ✓ {action.get('name')}: {len(links)} link(s)")
                for link in links:
                    vp_id = link.get("_from")
                    vp = vp_col.get(vp_id)
                    if vp:
                        print(f"      → Linked to: {vp.get('name')} (graphId: {vp.get('graphId')})")
            else:
                print(f"  ❌ {action.get('name')}: NO LINKS")
                unlinked_actions.append(action)
        
        # Fix unlinked actions
        if unlinked_actions:
            print(f"\n⚠️  Found {len(unlinked_actions)} unlinked action(s)")
            
            # Find default viewpoint for this graph
            default_vp = None
            for vp in viewpoints:
                if "Default" in vp.get("name", ""):
                    default_vp = vp
                    break
            
            if not default_vp and viewpoints:
                default_vp = viewpoints[0]  # Use first viewpoint if no "Default" found
            
            if default_vp:
                print(f"\nLinking unlinked actions to: {default_vp.get('name')}")
                from datetime import datetime
                now = datetime.utcnow().isoformat() + "Z"
                
                for action in unlinked_actions:
                    vp_act_col.insert({
                        "_from": default_vp["_id"],
                        "_to": action["_id"],
                        "createdAt": now,
                        "updatedAt": now
                    })
                    print(f"  ✓ Linked: {action.get('name')}")
            else:
                print(f"  ❌ No viewpoint found to link to")

if __name__ == "__main__":
    verify_viewpoint_links()
