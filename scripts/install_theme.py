import os
import json
import sys
import copy
from datetime import datetime
from dotenv import load_dotenv
from arango import ArangoClient

# Load environment variables
load_dotenv()

ARANGO_ENDPOINT = os.getenv("ARANGO_ENDPOINT")
ARANGO_USERNAME = os.getenv("ARANGO_USERNAME", "root")
ARANGO_PASSWORD = os.getenv("ARANGO_PASSWORD")
ARANGO_DATABASE = os.getenv("ARANGO_DATABASE", "risk-intelligence")

# File paths
THEME_FILES = [
    "docs/sentries_standard.json",
    "docs/sentries_risk_heatmap.json"
]

TARGET_GRAPHS = ["OntologyGraph", "DataGraph", "KnowledgeGraph"]

# Vertex collections we never want to show in Visualizer themes/actions.
# These are typically RDF-import artifacts and not user-facing concepts.
EXCLUDED_VERTEX_COLLECTIONS_BY_GRAPH = {
    "OntologyGraph": {"OntologyGraph_UnknownResource"},
}

def get_db():
    if not ARANGO_ENDPOINT or not ARANGO_PASSWORD:
        print("Error: ARANGO_ENDPOINT or ARANGO_PASSWORD not set.")
        sys.exit(1)
        
    client = ArangoClient(hosts=ARANGO_ENDPOINT)
    return client.db(ARANGO_DATABASE, username=ARANGO_USERNAME, password=ARANGO_PASSWORD)

def get_graph_schema(db, graph_name):
    """Fetches the actual vertex and edge collections for a graph."""
    if not db.has_graph(graph_name):
        return None, None
    
    graph = db.graph(graph_name)
    vertex_colls = set(graph.vertex_collections())
    vertex_colls -= EXCLUDED_VERTEX_COLLECTIONS_BY_GRAPH.get(graph_name, set())
    edge_definitions = graph.edge_definitions()
    edge_colls = set(ed['edge_collection'] for ed in edge_definitions)
    
    return vertex_colls, edge_colls

def install_canvas_actions(db, graph_name, vertex_colls, edge_colls):
    """Installs context-aware canvas actions tailored to the graph's schema."""
    # Ensure necessary collections exist
    for coll in ["_canvasActions", "_viewpoints"]:
        if not db.has_collection(coll):
            db.create_collection(coll, system=True)
    
    if not db.has_collection("_viewpointActions"):
        db.create_collection("_viewpointActions", edge=True, system=True)

    canvas_col = db.collection("_canvasActions")
    vp_col = db.collection("_viewpoints")
    vp_act_col = db.collection("_viewpointActions")

    # Remove obsolete "[Collection] Expand Relationships" actions if graph schema changed
    expected_action_names = {f"[{v}] Expand Relationships" for v in vertex_colls}
    existing_actions = list(canvas_col.find({"graphId": graph_name}))
    removed = 0
    for a in existing_actions:
        n = a.get("name") or ""
        if n.startswith("[") and n.endswith("] Expand Relationships"):
            if n not in expected_action_names:
                action_id = a.get("_id")
                if action_id:
                    # remove viewpoint links first
                    for edge in list(vp_act_col.find({"_to": action_id})):
                        try:
                            vp_act_col.delete(edge)
                        except Exception:
                            pass
                try:
                    canvas_col.delete(a)
                except Exception:
                    pass
                removed += 1
    if removed:
        print(f"    Removed {removed} obsolete canvas action(s) for {graph_name}")

    # 1. Ensure Default Viewpoint exists for the graph
    # Try "Default" first (this is what the UI uses)
    existing_vp = list(vp_col.find({"graphId": graph_name, "name": "Default"}))
    if not existing_vp:
        # Fallback to "Default - GraphName"
        vp_name = f"Default - {graph_name}"
        existing_vp = list(vp_col.find({"graphId": graph_name, "name": vp_name}))
    if not existing_vp:
        # Fallback to any viewpoint for this graph
        existing_vp = list(vp_col.find({"graphId": graph_name}))
    
    if not existing_vp:
        now = datetime.utcnow().isoformat() + "Z"
        vp_doc = {
            "graphId": graph_name,
            "name": "Default",  # Use "Default" not "Default - GraphName"
            "description": f"Default viewpoint for {graph_name}",
            "createdAt": now,
            "updatedAt": now
        }
        res = vp_col.insert(vp_doc)
        vp_id = res["_id"]
        print(f"    Created viewpoint: Default")
    else:
        vp_id = existing_vp[0]["_id"]
        vp_name_used = existing_vp[0].get("name", "Unknown")
        print(f"    Using viewpoint: {vp_name_used}")

    # 2. Create Canvas Actions only for vertex collections in this graph
    edge_list_str = ", ".join(edge_colls)
    
    actions_installed = 0
    for v_coll in vertex_colls:
        action_title = f"[{v_coll}] Expand Relationships"
        
        query = f"""FOR node IN @nodes
  FOR v, e, p IN 1..1 ANY node
    {edge_list_str}
    FILTER IS_SAME_COLLECTION("{v_coll}", v)
    LIMIT 20
    RETURN p"""

        now = datetime.utcnow().isoformat() + "Z"
        # Match working structure: no 'title' or 'query' fields, only 'queryText'
        # bindVariables.nodes should be empty string, not array
        action_doc = {
            "name": action_title,
            "description": f"Expand related entities for {v_coll}",
            "queryText": query,
            "graphId": graph_name,
            "bindVariables": {
                "nodes": ""
            },
            "updatedAt": now
        }

        # Update or Insert action
        existing_action = list(canvas_col.find({"name": action_title, "graphId": graph_name}))
        if existing_action:
            action_id = existing_action[0]["_id"]
            # Use replace() to ensure full document replacement (removes old fields like 'query' and 'title')
            action_doc["_key"] = existing_action[0]["_key"]
            action_doc["_id"] = existing_action[0]["_id"]
            canvas_col.replace(action_doc)
        else:
            action_doc["createdAt"] = now
            res = canvas_col.insert(action_doc)
            action_id = res["_id"]

        # 3. Link Action to Viewpoint
        edge_exists = list(vp_act_col.find({"_from": vp_id, "_to": action_id}))
        if not edge_exists:
            vp_act_col.insert({
                "_from": vp_id,
                "_to": action_id,
                "createdAt": now,
                "updatedAt": now
            })
        actions_installed += 1
    
    print(f"    Installed {actions_installed} canvas actions for {graph_name}")

def prune_theme(base_theme_raw, vertex_colls, edge_colls):
    """Removes configurations for collections not present in the graph schema."""
    # Use copy.deepcopy to ensure we are working on a fresh copy of the original theme
    theme = copy.deepcopy(base_theme_raw)
    
    # Prune node configurations
    if "nodeConfigMap" in theme:
        # Create a new dictionary with only valid nodes
        pruned_nodes = {}
        for node, config in theme["nodeConfigMap"].items():
            if node in vertex_colls:
                pruned_nodes[node] = config
        theme["nodeConfigMap"] = pruned_nodes
    
    # Prune edge configurations
    if "edgeConfigMap" in theme:
        pruned_edges = {}
        for edge, config in theme["edgeConfigMap"].items():
            if edge in edge_colls:
                pruned_edges[edge] = config
        theme["edgeConfigMap"] = pruned_edges
                
    return theme

DEMO_SCENARIOS_QUERY = """\
FOR doc IN UNION(
  (FOR d IN Person       FILTER d.dataSource == "Synthetic" RETURN d),
  (FOR d IN Organization FILTER d.dataSource == "Synthetic" RETURN d),
  (FOR d IN Vessel       FILTER d.dataSource == "Synthetic" RETURN d),
  (FOR d IN Aircraft     FILTER d.dataSource == "Synthetic" RETURN d)
)
RETURN doc"""

# Data-bearing graphs only (OntologyGraph has no instance data)
DEMO_ACTION_GRAPHS = {"DataGraph", "KnowledgeGraph"}


def install_demo_saved_query(db) -> None:
    """Upsert a saved AQL query so users can load synthetic nodes from the editor."""
    if not db.has_collection("_editor_saved_queries"):
        db.create_collection("_editor_saved_queries", system=True)

    col = db.collection("_editor_saved_queries")
    name = "Load Demo Scenarios"
    existing = list(col.find({"name": name}))
    doc = {
        "name": name,
        "value": DEMO_SCENARIOS_QUERY,
        "parameter": "{}",
    }
    if existing:
        doc["_key"] = existing[0]["_key"]
        doc["_id"] = existing[0]["_id"]
        col.replace(doc)
        print(f"  [Updated saved query] {name}")
    else:
        col.insert(doc)
        print(f"  [Installed saved query] {name}")


def install_demo_canvas_action(db, graph_name: str, vp_id: str) -> None:
    """Upsert a canvas-level action that loads all synthetic scenario nodes."""
    canvas_col = db.collection("_canvasActions")
    vp_act_col = db.collection("_viewpointActions")

    action_name = "Load Demo Scenarios"
    now = datetime.utcnow().isoformat() + "Z"
    action_doc = {
        "name": action_name,
        "description": "Bring all synthetic demo-scenario nodes onto the canvas",
        "queryText": DEMO_SCENARIOS_QUERY,
        "graphId": graph_name,
        "bindVariables": {},
        "updatedAt": now,
    }

    existing = list(canvas_col.find({"name": action_name, "graphId": graph_name}))
    if existing:
        action_doc["_key"] = existing[0]["_key"]
        action_doc["_id"] = existing[0]["_id"]
        canvas_col.replace(action_doc)
        action_id = existing[0]["_id"]
    else:
        action_doc["createdAt"] = now
        res = canvas_col.insert(action_doc)
        action_id = res["_id"]
        print(f"    [Installed canvas action] {action_name} → {graph_name}")

    # Link to viewpoint if not already linked
    if not list(vp_act_col.find({"_from": vp_id, "_to": action_id})):
        vp_act_col.insert({"_from": vp_id, "_to": action_id, "createdAt": now, "updatedAt": now})


def install_themes():
    db = get_db()
    
    if not db.has_collection("_graphThemeStore"):
        db.create_collection("_graphThemeStore", system=True)
        print("Created collection: _graphThemeStore")
    
    theme_col = db.collection("_graphThemeStore")
    
    print(f"\nInstalling Tailored Themes for database: {ARANGO_DATABASE}")
    print("=" * 80)
    
    # Load all themes into memory first to avoid re-reading files in the loop
    themes_in_memory = []
    for theme_path in THEME_FILES:
        if not os.path.exists(theme_path):
            print(f"Error: Theme file not found: {theme_path}")
            continue
        with open(theme_path, 'r') as f:
            themes_in_memory.append(json.load(f))
            
    for base_theme in themes_in_memory:
        print(f"\nProcessing Theme: {base_theme.get('name')}")
        print("-" * 40)
        
        for g_id in TARGET_GRAPHS:
            # 1. Introspect graph schema
            vertex_colls, edge_colls = get_graph_schema(db, g_id)
            if vertex_colls is None:
                print(f"  [SKIP] Graph '{g_id}' does not exist")
                continue

            # Special logic for OntologyGraph themes
            if g_id == "OntologyGraph":
                # Only install 'sentries_standard' for OntologyGraph, but rename it to 'Ontology'
                if base_theme.get('name') != 'sentries_standard':
                    print(f"  [SKIP] Theme '{base_theme.get('name')}' is irrelevant for OntologyGraph")
                    continue
                
                theme = prune_theme(base_theme, vertex_colls, edge_colls)
                theme["name"] = "Ontology"
                theme["description"] = "Standard Ontology visual configuration"
            else:
                # Normal pruning for other graphs
                theme = prune_theme(base_theme, vertex_colls, edge_colls)

            theme["graphId"] = g_id
            now = datetime.utcnow().isoformat() + "Z"
            theme["createdAt"] = now
            theme["updatedAt"] = now
            
            # Set isDefault explicitly: only Default themes or Ontology theme should be default
            # For OntologyGraph, the "Ontology" theme is the default (renamed from sentries_standard)
            # For other graphs, only "Default" theme should be default
            if g_id == "OntologyGraph" and theme["name"] == "Ontology":
                theme["isDefault"] = True
            elif theme["name"] == "Default":
                theme["isDefault"] = True
            else:
                theme["isDefault"] = False
            
            # 3. Install/Update Tailored Theme
            # Ensure required fields exist to match working database structure
            # This ensures compatibility with ArangoDB Visualizer expectations
            
            # For node configs: ensure rules and hoverInfoAttributes exist
            if "nodeConfigMap" in theme:
                for node_type, node_config in theme["nodeConfigMap"].items():
                    if "rules" not in node_config:
                        node_config["rules"] = []
                    if "hoverInfoAttributes" not in node_config:
                        node_config["hoverInfoAttributes"] = []
            
            # For edge configs: ensure all optional but recommended fields exist
            # The working 'test' theme shows these fields are needed for proper rendering
            if "edgeConfigMap" in theme:
                for edge_type, edge_config in theme["edgeConfigMap"].items():
                    if "rules" not in edge_config:
                        edge_config["rules"] = []
                    if "hoverInfoAttributes" not in edge_config:
                        edge_config["hoverInfoAttributes"] = []
                    # Add arrowStyle if missing (needed for proper edge rendering)
                    if "arrowStyle" not in edge_config:
                        edge_config["arrowStyle"] = {
                            "sourceArrowShape": "none",
                            "targetArrowShape": "triangle"
                        }
                    # Add labelStyle if missing (for edge label styling)
                    if "labelStyle" not in edge_config:
                        edge_config["labelStyle"] = {
                            "color": "#1d2531"
                        }
            
            existing = list(theme_col.find({"name": theme["name"], "graphId": g_id}))
            if existing:
                # Use replace() instead of update() to ensure full document replacement
                # This ensures all fields from source are properly stored, including rules
                theme["_key"] = existing[0]["_key"]
                theme["_id"] = existing[0]["_id"]
                theme_col.replace(theme)
                print(f"  [Updated Theme] Graph: {g_id}, Name: {theme['name']} (Tailored: {len(theme.get('nodeConfigMap',{}))} nodes, {len(theme.get('edgeConfigMap',{}))} edges)")
            else:
                theme_col.insert(theme)
                print(f"  [Installed Theme] Graph: {g_id}, Name: {theme['name']} (Tailored: {len(theme.get('nodeConfigMap',{}))} nodes, {len(theme.get('edgeConfigMap',{}))} edges)")
            
            # 4. Install Tailored Canvas Actions (per-collection Expand actions)
            install_canvas_actions(db, g_id, vertex_colls, edge_colls)

            # 5. Install "Load Demo Scenarios" canvas action for data-bearing graphs
            if g_id in DEMO_ACTION_GRAPHS:
                # Resolve the viewpoint id (same logic as install_canvas_actions)
                vp_col = db.collection("_viewpoints")
                vp_docs = (
                    list(vp_col.find({"graphId": g_id, "name": "Default"}))
                    or list(vp_col.find({"graphId": g_id}))
                )
                if vp_docs:
                    install_demo_canvas_action(db, g_id, vp_docs[0]["_id"])

    # Install the AQL editor saved query once (not per-graph)
    print("\nInstalling demo saved query...")
    install_demo_saved_query(db)

    print("\n" + "="*80)
    print("Tailored Theme & Canvas Action Installation Complete")

if __name__ == "__main__":
    install_themes()
