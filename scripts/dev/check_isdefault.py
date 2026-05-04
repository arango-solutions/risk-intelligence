import os
from dotenv import load_dotenv
from arango import ArangoClient
import json

# Load environment variables
load_dotenv()

ARANGO_ENDPOINT = os.getenv("ARANGO_ENDPOINT")
ARANGO_USERNAME = os.getenv("ARANGO_USERNAME", "root")
ARANGO_PASSWORD = os.getenv("ARANGO_PASSWORD")

def check_isdefault_field():
    """Check isDefault field on all themes in both databases."""
    client = ArangoClient(hosts=ARANGO_ENDPOINT)
    
    for db_name in ["themes", "risk-management"]:
        db = client.db(db_name, username=ARANGO_USERNAME, password=ARANGO_PASSWORD)
        
        if not db.has_collection("_graphThemeStore"):
            print(f"\n{db_name}: No _graphThemeStore")
            continue
        
        theme_col = db.collection("_graphThemeStore")
        all_themes = list(theme_col.all())
        
        print(f"\n{'='*80}")
        print(f"{db_name.upper()} DATABASE")
        print(f"{'='*80}\n")
        
        for theme in all_themes:
            graph_id = theme.get('graphId')
            name = theme.get('name')
            is_default = theme.get('isDefault')
            has_field = 'isDefault' in theme
            
            status = "✓" if has_field else "✗"
            value_str = f"={is_default}" if has_field else "(missing)"
            
            print(f"{status} {graph_id} / {name}: isDefault {value_str}")

if __name__ == "__main__":
    check_isdefault_field()
