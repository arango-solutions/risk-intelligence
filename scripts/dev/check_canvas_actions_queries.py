import os
from dotenv import load_dotenv
from arango import ArangoClient

# Load environment variables
load_dotenv()

ARANGO_ENDPOINT = os.getenv("ARANGO_ENDPOINT")
ARANGO_USERNAME = os.getenv("ARANGO_USERNAME", "root")
ARANGO_PASSWORD = os.getenv("ARANGO_PASSWORD")
ARANGO_DATABASE = os.getenv("ARANGO_DATABASE", "risk-management")

def check_canvas_actions_queries():
    """Check if canvas actions and stored queries are installed."""
    client = ArangoClient(hosts=ARANGO_ENDPOINT)
    db = client.db(ARANGO_DATABASE, username=ARANGO_USERNAME, password=ARANGO_PASSWORD)
    
    print(f"\n{'='*80}")
    print("CHECKING CANVAS ACTIONS AND STORED QUERIES")
    print(f"{'='*80}\n")
    
    # Check canvas actions
    print("CANVAS ACTIONS:")
    print("-" * 80)
    
    if not db.has_collection("_canvasActions"):
        print("  ❌ _canvasActions collection does not exist")
    else:
        canvas_col = db.collection("_canvasActions")
        all_actions = list(canvas_col.all())
        
        print(f"  ✓ Found {len(all_actions)} canvas action(s)")
        
        # Group by graph
        actions_by_graph = {}
        for action in all_actions:
            graph_id = action.get("graphId", "NO_GRAPH")
            if graph_id not in actions_by_graph:
                actions_by_graph[graph_id] = []
            actions_by_graph[graph_id].append(action)
        
        for graph_id, actions in actions_by_graph.items():
            print(f"\n  {graph_id}: {len(actions)} action(s)")
            for action in actions:
                print(f"    - {action.get('name', 'UNNAMED')}")
    
    # Check viewpoints
    print(f"\n\nVIEWPOINTS:")
    print("-" * 80)
    
    if not db.has_collection("_viewpoints"):
        print("  ❌ _viewpoints collection does not exist")
    else:
        vp_col = db.collection("_viewpoints")
        all_viewpoints = list(vp_col.all())
        
        print(f"  ✓ Found {len(all_viewpoints)} viewpoint(s)")
        
        for vp in all_viewpoints:
            print(f"    - {vp.get('name')} (graphId: {vp.get('graphId')})")
    
    # Check viewpoint actions (edges linking viewpoints to actions)
    print(f"\n\nVIEWPOINT-ACTION LINKS:")
    print("-" * 80)
    
    if not db.has_collection("_viewpointActions"):
        print("  ❌ _viewpointActions collection does not exist")
    else:
        vp_act_col = db.collection("_viewpointActions")
        all_links = list(vp_act_col.all())
        
        print(f"  ✓ Found {len(all_links)} viewpoint-action link(s)")
    
    # Check stored queries
    print(f"\n\nSTORED QUERIES:")
    print("-" * 80)
    
    if not db.has_collection("_editor_saved_queries"):
        print("  ❌ _editor_saved_queries collection does not exist")
        print("  → Run: python3 scripts/install_dashboard.py")
    else:
        query_col = db.collection("_editor_saved_queries")
        all_queries = list(query_col.all())
        
        print(f"  ✓ Found {len(all_queries)} stored query/queries")
        
        for query in all_queries:
            print(f"    - {query.get('name', 'UNNAMED')}")
    
    # Summary
    print(f"\n\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}\n")
    
    has_canvas_actions = db.has_collection("_canvasActions") and len(list(db.collection("_canvasActions").all())) > 0
    has_viewpoints = db.has_collection("_viewpoints") and len(list(db.collection("_viewpoints").all())) > 0
    has_stored_queries = db.has_collection("_editor_saved_queries") and len(list(db.collection("_editor_saved_queries").all())) > 0
    
    if has_canvas_actions and has_viewpoints:
        print("✅ Canvas Actions: Installed")
    else:
        print("❌ Canvas Actions: Missing or incomplete")
        print("  → Run: python3 scripts/install_theme.py")
    
    if has_stored_queries:
        print("✅ Stored Queries: Installed")
    else:
        print("❌ Stored Queries: Missing")
        print("  → Run: python3 scripts/install_dashboard.py")

if __name__ == "__main__":
    check_canvas_actions_queries()
