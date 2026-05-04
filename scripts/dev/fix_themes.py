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

def fix_themes():
    """Fix isDefault field on all themes in risk-management database."""
    client = ArangoClient(hosts=ARANGO_ENDPOINT)
    db = client.db(ARANGO_DATABASE, username=ARANGO_USERNAME, password=ARANGO_PASSWORD)
    
    if not db.has_collection("_graphThemeStore"):
        print("❌ _graphThemeStore collection does not exist")
        return
    
    theme_col = db.collection("_graphThemeStore")
    all_themes = list(theme_col.all())
    
    print(f"\n{'='*80}")
    print(f"FIXING THEMES IN DATABASE: {ARANGO_DATABASE}")
    print(f"{'='*80}\n")
    
    # Group themes by graphId
    themes_by_graph = {}
    for theme in all_themes:
        graph_id = theme.get('graphId')
        if graph_id not in themes_by_graph:
            themes_by_graph[graph_id] = []
        themes_by_graph[graph_id].append(theme)
    
    updated_count = 0
    
    for graph_id, themes in themes_by_graph.items():
        print(f"\nProcessing Graph: {graph_id}")
        print(f"  Found {len(themes)} theme(s)")
        
        # Determine which theme should be default
        # For OntologyGraph: "Ontology" theme is default
        # For other graphs: "Default" theme is default
        default_theme_name = "Ontology" if graph_id == "OntologyGraph" else "Default"
        
        default_theme = None
        for theme in themes:
            if theme.get('name') == default_theme_name:
                default_theme = theme
                break
        
        # Update all themes in this graph
        for theme in themes:
            theme_name = theme.get('name')
            should_be_default = (theme == default_theme) if default_theme else False
            
            current_is_default = theme.get('isDefault')
            needs_update = False
            new_is_default = should_be_default
            
            # Check if update is needed
            if should_be_default:
                if current_is_default != True:
                    needs_update = True
            else:
                # Need to explicitly set False if missing or not False
                if 'isDefault' not in theme or current_is_default != False:
                    needs_update = True
            
            if needs_update:
                # Read the full document to ensure we have all fields
                full_theme = theme_col.get(theme["_key"])
                if full_theme:
                    full_theme["isDefault"] = new_is_default
                    full_theme["updatedAt"] = datetime.utcnow().isoformat() + "Z"
                    theme_col.update(full_theme)
                    print(f"  → Setting isDefault={new_is_default} for '{theme_name}' theme")
                    updated_count += 1
        
        if not needs_update:
            print(f"  ✓ All themes already have correct isDefault values")
    
    print(f"\n{'='*80}")
    print(f"FIX COMPLETE: Updated {updated_count} theme(s)")
    print(f"{'='*80}\n")
    
    # Verify the fix by re-reading from database
    print("Verification - Current theme state (re-read from database):")
    all_themes_after = list(theme_col.all())
    themes_by_graph_after = {}
    for theme in all_themes_after:
        graph_id = theme.get('graphId')
        if graph_id not in themes_by_graph_after:
            themes_by_graph_after[graph_id] = []
        themes_by_graph_after[graph_id].append(theme)
    
    for graph_id, themes in themes_by_graph_after.items():
        default_themes = [t for t in themes if t.get('isDefault') == True]
        non_default_themes = [t for t in themes if t.get('isDefault') == False]
        missing_field = [t for t in themes if 'isDefault' not in t]
        
        print(f"  {graph_id}:")
        print(f"    Default themes (isDefault=true): {len(default_themes)}")
        for dt in default_themes:
            print(f"      - {dt.get('name')}")
        print(f"    Non-default themes (isDefault=false): {len(non_default_themes)}")
        for ndt in non_default_themes:
            print(f"      - {ndt.get('name')}")
        if missing_field:
            print(f"    ⚠️  Themes missing isDefault field: {len(missing_field)}")
            for mf in missing_field:
                print(f"      - {mf.get('name')}")

if __name__ == "__main__":
    fix_themes()
