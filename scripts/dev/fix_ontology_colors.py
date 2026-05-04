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

def fix_ontology_colors():
    """Update Ontology theme to make ObjectProperty and DatatypeProperty different colors."""
    client = ArangoClient(hosts=ARANGO_ENDPOINT)
    db = client.db(ARANGO_DATABASE, username=ARANGO_USERNAME, password=ARANGO_PASSWORD)
    theme_col = db.collection("_graphThemeStore")
    
    # Get Ontology theme
    ontology_theme = list(theme_col.find({
        "graphId": "OntologyGraph",
        "name": "Ontology"
    }))
    
    if not ontology_theme:
        print("❌ 'Ontology' theme not found")
        return
    
    ontology_theme = ontology_theme[0]
    
    print(f"\n{'='*80}")
    print("UPDATING ONTOLOGY THEME COLORS")
    print(f"{'='*80}\n")
    
    node_configs = ontology_theme.get("nodeConfigMap", {})
    
    # Check current ObjectProperty color
    if "ObjectProperty" in node_configs:
        current_color = node_configs["ObjectProperty"].get("background", {}).get("color")
        print(f"Current ObjectProperty color: {current_color}")
    
    # Update ObjectProperty to a different color (orange/yellow to distinguish from green Property)
    if "ObjectProperty" in node_configs:
        node_configs["ObjectProperty"]["background"]["color"] = "#d69e2e"  # Yellow/orange
        print(f"  → Changed ObjectProperty color to: #d69e2e (yellow/orange)")
    
    # Check if DatatypeProperty exists, if not add it with a different color
    if "DatatypeProperty" not in node_configs:
        # Add DatatypeProperty config (different color - blue/teal)
        node_configs["DatatypeProperty"] = {
            "background": {
                "color": "#319795",  # Teal/cyan
                "iconName": "fa6-solid:link"
            },
            "labelAttribute": "label",
            "hoverInfoAttributes": [
                "label",
                "_id"
            ],
            "rules": []
        }
        print(f"  → Added DatatypeProperty with color: #319795 (teal/cyan)")
    else:
        # Update existing DatatypeProperty to a different color
        node_configs["DatatypeProperty"]["background"]["color"] = "#319795"  # Teal/cyan
        print(f"  → Updated DatatypeProperty color to: #319795 (teal/cyan)")
    
    # Update the theme in database
    ontology_theme["updatedAt"] = datetime.utcnow().isoformat() + "Z"
    theme_col.replace(ontology_theme)
    
    print(f"\n✅ Ontology theme updated successfully!")
    print(f"\nColor Summary:")
    print(f"  Property: #48bb78 (green)")
    print(f"  ObjectProperty: #d69e2e (yellow/orange)")
    print(f"  DatatypeProperty: #319795 (teal/cyan)")

if __name__ == "__main__":
    fix_ontology_colors()
