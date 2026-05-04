import os
import json
from dotenv import load_dotenv
from arango import ArangoClient
from datetime import datetime

# Load environment variables
load_dotenv()

ARANGO_ENDPOINT = os.getenv("ARANGO_ENDPOINT")
ARANGO_USERNAME = os.getenv("ARANGO_USERNAME", "root")
ARANGO_PASSWORD = os.getenv("ARANGO_PASSWORD")
ARANGO_DATABASE = os.getenv("ARANGO_DATABASE", "risk-management")

def fix_canvas_actions():
    """Fix our canvas actions to match the working structure."""
    client = ArangoClient(hosts=ARANGO_ENDPOINT)
    db = client.db(ARANGO_DATABASE, username=ARANGO_USERNAME, password=ARANGO_PASSWORD)
    
    print(f"\n{'='*80}")
    print("FIXING CANVAS ACTIONS TO MATCH WORKING STRUCTURE")
    print(f"{'='*80}\n")
    
    if not db.has_collection("_canvasActions"):
        print("❌ _canvasActions collection does not exist")
        return
    
    canvas_col = db.collection("_canvasActions")
    
    # Get working action as reference
    working_action = list(canvas_col.find({
        "graphId": "OntologyGraph",
        "name": "Find 3 Hop Neighbor"
    }))
    
    if not working_action:
        print("⚠️  Working action not found for reference")
        return
    
    working_action = working_action[0]
    
    print("Working action structure (reference):")
    print(json.dumps({k: v for k, v in working_action.items() if k not in ['_id', '_key', '_rev']}, indent=2))
    
    # Get our custom actions
    all_actions = list(canvas_col.find({"graphId": "OntologyGraph"}))
    our_actions = [a for a in all_actions if "[Class]" in a.get("name", "") or "[Property]" in a.get("name", "") or "[ObjectProperty]" in a.get("name", "")]
    
    print(f"\n\nFound {len(our_actions)} custom actions to fix\n")
    
    fixed_count = 0
    for action in our_actions:
        name = action.get("name")
        print(f"Fixing: {name}")
        
        # Remove 'query' field (keep only queryText)
        if "query" in action:
            del action["query"]
            print(f"  → Removed 'query' field")
        
        # Remove 'title' field
        if "title" in action:
            del action["title"]
            print(f"  → Removed 'title' field")
        
        # Fix bindVariables.nodes to be empty string instead of array
        if "bindVariables" in action:
            if isinstance(action["bindVariables"].get("nodes"), list):
                action["bindVariables"]["nodes"] = ""
                print(f"  → Changed bindVariables.nodes from [] to ''")
        
        # Update timestamp
        action["updatedAt"] = datetime.utcnow().isoformat() + "Z"
        
        # Save
        canvas_col.replace(action)
        fixed_count += 1
        print(f"  ✓ Fixed\n")
    
    print(f"{'='*80}")
    print(f"Fixed {fixed_count} canvas action(s)")
    print(f"{'='*80}\n")
    
    # Verify
    print("Verification - Sample fixed action:")
    if our_actions:
        fixed_action = canvas_col.get(our_actions[0]["_key"])
        print(json.dumps({k: v for k, v in fixed_action.items() if k not in ['_id', '_key', '_rev']}, indent=2))

if __name__ == "__main__":
    fix_canvas_actions()
