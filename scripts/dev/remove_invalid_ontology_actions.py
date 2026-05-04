import os
from dotenv import load_dotenv
from arango import ArangoClient

# Load environment variables
load_dotenv()

ARANGO_ENDPOINT = os.getenv("ARANGO_ENDPOINT")
ARANGO_USERNAME = os.getenv("ARANGO_USERNAME", "root")
ARANGO_PASSWORD = os.getenv("ARANGO_PASSWORD")
ARANGO_DATABASE = os.getenv("ARANGO_DATABASE", "risk-management")

def remove_invalid_ontology_actions():
    """Remove Aircraft, Person, and Vessel canvas actions from OntologyGraph."""
    client = ArangoClient(hosts=ARANGO_ENDPOINT)
    db = client.db(ARANGO_DATABASE, username=ARANGO_USERNAME, password=ARANGO_PASSWORD)
    
    print(f"\n{'='*80}")
    print("REMOVING INVALID CANVAS ACTIONS FROM ONTOLOGYGRAPH")
    print(f"{'='*80}\n")
    
    if not db.has_collection("_canvasActions"):
        print("❌ _canvasActions collection does not exist")
        return
    
    canvas_col = db.collection("_canvasActions")
    vp_act_col = db.collection("_viewpointActions")
    
    # Actions to remove
    actions_to_remove = [
        "[Aircraft] Expand Relationships",
        "[Person] Expand Relationships",
        "[Vessel] Expand Relationships"
    ]
    
    print(f"Removing {len(actions_to_remove)} action(s) from OntologyGraph:\n")
    
    removed_count = 0
    for action_name in actions_to_remove:
        # Find the action
        actions = list(canvas_col.find({
            "graphId": "OntologyGraph",
            "name": action_name
        }))
        
        if actions:
            action = actions[0]
            action_id = action["_id"]
            
            print(f"Removing: {action_name}")
            
            # Remove viewpoint links first
            links = list(vp_act_col.find({"_to": action_id}))
            for link in links:
                vp_act_col.delete(link["_key"])
                print(f"  → Removed viewpoint link")
            
            # Remove the action
            canvas_col.delete(action["_key"])
            print(f"  ✓ Removed action")
            removed_count += 1
        else:
            print(f"⚠️  {action_name}: Not found (may already be removed)")
    
    print(f"\n{'='*80}")
    print(f"Removed {removed_count} action(s)")
    print(f"{'='*80}\n")
    
    # Verify remaining actions
    remaining_actions = list(canvas_col.find({"graphId": "OntologyGraph"}))
    custom_actions = [a for a in remaining_actions if "2-hop neighbors" not in a.get("name", "") and "default" not in a.get("name", "").lower()]
    
    print(f"Remaining OntologyGraph actions: {len(custom_actions)}")
    for action in custom_actions:
        print(f"  - {action.get('name')}")

if __name__ == "__main__":
    remove_invalid_ontology_actions()
