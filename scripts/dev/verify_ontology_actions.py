import os
from dotenv import load_dotenv
from arango import ArangoClient

# Load environment variables
load_dotenv()

ARANGO_ENDPOINT = os.getenv("ARANGO_ENDPOINT")
ARANGO_USERNAME = os.getenv("ARANGO_USERNAME", "root")
ARANGO_PASSWORD = os.getenv("ARANGO_PASSWORD")
ARANGO_DATABASE = os.getenv("ARANGO_DATABASE", "risk-management")

def verify_ontology_actions():
    """Verify that OntologyGraph actions match the actual vertex collections."""
    client = ArangoClient(hosts=ARANGO_ENDPOINT)
    db = client.db(ARANGO_DATABASE, username=ARANGO_USERNAME, password=ARANGO_PASSWORD)
    
    print(f"\n{'='*80}")
    print("VERIFYING ONTOLOGYGRAPH ACTIONS")
    print(f"{'='*80}\n")
    
    # Get actual vertex collections in OntologyGraph
    if not db.has_graph("OntologyGraph"):
        print("❌ OntologyGraph does not exist")
        return
    
    graph = db.graph("OntologyGraph")
    vertex_colls = set(graph.vertex_collections())
    
    print(f"Actual vertex collections in OntologyGraph:")
    for coll in sorted(vertex_colls):
        print(f"  - {coll}")
    
    # Get current canvas actions
    canvas_col = db.collection("_canvasActions")
    all_actions = list(canvas_col.find({"graphId": "OntologyGraph"}))
    custom_actions = [a for a in all_actions if "Expand Relationships" in a.get("name", "")]
    
    print(f"\n\nCurrent canvas actions:")
    for action in custom_actions:
        name = action.get("name", "")
        # Extract collection name from "[Collection] Expand Relationships"
        if "[" in name and "]" in name:
            coll_name = name.split("[")[1].split("]")[0]
            if coll_name in vertex_colls:
                print(f"  ✓ {name} (valid)")
            else:
                print(f"  ❌ {name} (INVALID - collection not in graph)")
        else:
            print(f"  ? {name} (unknown format)")
    
    # Check if Organization should be removed
    if "Organization" not in vertex_colls:
        print(f"\n⚠️  'Organization' is not in OntologyGraph vertex collections")
        print(f"   Should we remove '[Organization] Expand Relationships' action?")

if __name__ == "__main__":
    verify_ontology_actions()
