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

def fix_all_canvas_actions():
    """Fix ALL canvas actions across all graphs to match working structure."""
    client = ArangoClient(hosts=ARANGO_ENDPOINT)
    db = client.db(ARANGO_DATABASE, username=ARANGO_USERNAME, password=ARANGO_PASSWORD)
    
    print(f"\n{'='*80}")
    print("FIXING ALL CANVAS ACTIONS ACROSS ALL GRAPHS")
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
        # Use default action as reference instead
        working_action = list(canvas_col.find({
            "graphId": "OntologyGraph",
            "name": {"$like": "%2-hop neighbors%"}
        }))
    
    if working_action:
        working_action = working_action[0]
        print("Working action structure (reference):")
        print(json.dumps({k: v for k, v in working_action.items() if k not in ['_id', '_key', '_rev']}, indent=2))
    
    # Get ALL custom actions (exclude default "2-hop neighbors" actions)
    all_actions = list(canvas_col.all())
    
    # Filter out default actions
    custom_actions = []
    for action in all_actions:
        name = action.get("name", "")
        # Exclude default actions
        if "2-hop neighbors" not in name and "default" not in name.lower():
            custom_actions.append(action)
    
    print(f"\n\nFound {len(custom_actions)} custom actions to fix across all graphs\n")
    
    # Group by graph
    actions_by_graph = {}
    for action in custom_actions:
        graph_id = action.get("graphId", "NO_GRAPH")
        if graph_id not in actions_by_graph:
            actions_by_graph[graph_id] = []
        actions_by_graph[graph_id].append(action)
    
    fixed_count = 0
    for graph_id, actions in actions_by_graph.items():
        print(f"\n{'='*80}")
        print(f"Processing {graph_id}: {len(actions)} action(s)")
        print(f"{'='*80}\n")
        
        for action in actions:
            name = action.get("name")
            print(f"Fixing: {name}")
            
            changes = []
            
            # Remove 'query' field (keep only queryText)
            if "query" in action:
                del action["query"]
                changes.append("removed 'query' field")
            
            # Remove 'title' field
            if "title" in action:
                del action["title"]
                changes.append("removed 'title' field")
            
            # Fix bindVariables.nodes to be empty string instead of array
            if "bindVariables" in action:
                nodes_val = action["bindVariables"].get("nodes")
                if isinstance(nodes_val, list):
                    action["bindVariables"]["nodes"] = ""
                    changes.append("changed bindVariables.nodes from [] to ''")
                elif nodes_val is None:
                    action["bindVariables"]["nodes"] = ""
                    changes.append("set bindVariables.nodes to ''")
            
            if changes:
                # Update timestamp
                action["updatedAt"] = datetime.utcnow().isoformat() + "Z"
                
                # Save
                canvas_col.replace(action)
                fixed_count += 1
                print(f"  → {'; '.join(changes)}")
                print(f"  ✓ Fixed\n")
            else:
                print(f"  ✓ Already correct\n")
    
    print(f"\n{'='*80}")
    print(f"Fixed {fixed_count} canvas action(s) across all graphs")
    print(f"{'='*80}\n")
    
    # Summary by graph
    print("Summary by graph:")
    for graph_id, actions in actions_by_graph.items():
        print(f"  {graph_id}: {len(actions)} action(s)")

if __name__ == "__main__":
    fix_all_canvas_actions()
