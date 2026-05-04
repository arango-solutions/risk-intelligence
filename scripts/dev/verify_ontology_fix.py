import os
import json
from dotenv import load_dotenv
from arango import ArangoClient

# Load environment variables
load_dotenv()

ARANGO_ENDPOINT = os.getenv("ARANGO_ENDPOINT")
ARANGO_USERNAME = os.getenv("ARANGO_USERNAME", "root")
ARANGO_PASSWORD = os.getenv("ARANGO_PASSWORD")
ARANGO_DATABASE = os.getenv("ARANGO_DATABASE", "risk-management")

def verify_ontology_fix():
    """Verify that Ontology theme now has all required fields."""
    client = ArangoClient(hosts=ARANGO_ENDPOINT)
    db = client.db(ARANGO_DATABASE, username=ARANGO_USERNAME, password=ARANGO_PASSWORD)
    theme_col = db.collection("_graphThemeStore")
    
    ontology_theme = list(theme_col.find({
        "graphId": "OntologyGraph",
        "name": "Ontology"
    }))
    
    if not ontology_theme:
        print("❌ 'Ontology' theme not found")
        return
    
    ontology_theme = ontology_theme[0]
    
    print(f"\n{'='*80}")
    print("VERIFYING ONTOLOGY THEME FIX")
    print(f"{'='*80}\n")
    
    # Check edge configs
    edge_configs = ontology_theme.get("edgeConfigMap", {})
    
    print("Edge Config Verification:")
    print("-" * 80)
    
    required_edge_fields = ["arrowStyle", "labelStyle", "hoverInfoAttributes", "rules"]
    all_good = True
    
    for edge_type, edge_config in edge_configs.items():
        print(f"\n{edge_type}:")
        missing = []
        for field in required_edge_fields:
            if field in edge_config:
                print(f"  ✓ {field}: present")
            else:
                print(f"  ✗ {field}: MISSING")
                missing.append(field)
                all_good = False
        
        if missing:
            print(f"  ⚠️  Missing fields: {missing}")
        else:
            print(f"  ✓ All required fields present")
    
    # Check node configs
    node_configs = ontology_theme.get("nodeConfigMap", {})
    
    print(f"\n\nNode Config Verification:")
    print("-" * 80)
    
    required_node_fields = ["rules", "hoverInfoAttributes"]
    
    for node_type, node_config in node_configs.items():
        print(f"\n{node_type}:")
        missing = []
        for field in required_node_fields:
            if field in node_config:
                print(f"  ✓ {field}: present")
            else:
                print(f"  ✗ {field}: MISSING")
                missing.append(field)
                all_good = False
        
        if missing:
            print(f"  ⚠️  Missing fields: {missing}")
        else:
            print(f"  ✓ All required fields present")
    
    print(f"\n{'='*80}")
    if all_good:
        print("✅ ALL REQUIRED FIELDS ARE PRESENT")
    else:
        print("❌ SOME REQUIRED FIELDS ARE MISSING")
    print(f"{'='*80}\n")
    
    # Show sample edge config
    if edge_configs:
        sample_edge = list(edge_configs.items())[0]
        print(f"Sample edge config ({sample_edge[0]}):")
        print(json.dumps(sample_edge[1], indent=2))

if __name__ == "__main__":
    verify_ontology_fix()
