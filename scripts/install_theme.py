#!/usr/bin/env python3
"""
Install ArangoDB Graph Visualizer themes, canvas actions, and saved queries
for the risk-intelligence database.

Run as the last step in the pipeline (or standalone):
    python scripts/install_theme.py
"""

import copy
import json
import os
import re
import sys
from datetime import datetime
from typing import Dict, Set

from dotenv import load_dotenv
from arango import ArangoClient

load_dotenv()

ARANGO_ENDPOINT = os.getenv("ARANGO_ENDPOINT")
ARANGO_USERNAME = os.getenv("ARANGO_USERNAME", "root")
ARANGO_PASSWORD = os.getenv("ARANGO_PASSWORD")
ARANGO_DATABASE = os.getenv("ARANGO_DATABASE", "risk-intelligence")

THEME_FILES = [
    "docs/sentries_standard.json",
    "docs/sentries_risk_heatmap.json",
]

# Graphs that get the risk-heatmap as their default theme (and receive
# the demo-scenarios canvas action + Visualizer query panel entry).
DATA_GRAPHS = {"DataGraph", "KnowledgeGraph"}

# Vertex collections we never want in Visualizer themes or actions —
# typically RDF-import artifacts.
EXCLUDED_VERTEX_COLLECTIONS_BY_GRAPH: Dict[str, Set[str]] = {
    "OntologyGraph": {"OntologyGraph_UnknownResource"},
}

TARGET_GRAPHS = ["OntologyGraph", "DataGraph", "KnowledgeGraph"]

# AQL text for the "Load Demo Scenarios" feature
DEMO_SCENARIOS_QUERY = """\
FOR doc IN UNION(
  (FOR d IN Person       FILTER d.dataSource == "Synthetic" RETURN d),
  (FOR d IN Organization FILTER d.dataSource == "Synthetic" RETURN d),
  (FOR d IN Vessel       FILTER d.dataSource == "Synthetic" RETURN d),
  (FOR d IN Aircraft     FILTER d.dataSource == "Synthetic" RETURN d)
)
RETURN doc"""


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

def get_db():
    if not ARANGO_ENDPOINT or not ARANGO_PASSWORD:
        print("Error: ARANGO_ENDPOINT or ARANGO_PASSWORD not set.")
        sys.exit(1)
    client = ArangoClient(hosts=ARANGO_ENDPOINT)
    return client.db(ARANGO_DATABASE, username=ARANGO_USERNAME, password=ARANGO_PASSWORD)


# ---------------------------------------------------------------------------
# Collection / viewpoint helpers
# ---------------------------------------------------------------------------

def ensure_collection(db, name: str, edge: bool = False) -> None:
    if not db.has_collection(name):
        db.create_collection(name, edge=edge, system=name.startswith("_"))


def ensure_default_viewpoint(db, graph_name: str) -> str:
    """Return the _id of the Default viewpoint, creating it if absent."""
    ensure_collection(db, "_viewpoints")
    vp_col = db.collection("_viewpoints")

    # Try exact "Default" first; fall back to any viewpoint for this graph.
    for query in [
        {"graphId": graph_name, "name": "Default"},
        {"graphId": graph_name},
    ]:
        existing = list(vp_col.find(query))
        if existing:
            print(f"    Using viewpoint: {existing[0].get('name', '?')} ({graph_name})")
            return existing[0]["_id"]

    now = datetime.utcnow().isoformat() + "Z"
    res = vp_col.insert({
        "graphId": graph_name,
        "name": "Default",
        "description": f"Default viewpoint for {graph_name}",
        "createdAt": now,
        "updatedAt": now,
    })
    print(f"    Created viewpoint: Default ({graph_name})")
    return res["_id"]


# ---------------------------------------------------------------------------
# Theme helpers
# ---------------------------------------------------------------------------

def get_graph_schema(db, graph_name: str):
    """Return (vertex_colls, edge_colls) sets for graph_name, or (None, None)."""
    if not db.has_graph(graph_name):
        return None, None
    g = db.graph(graph_name)
    vertex_colls = set(g.vertex_collections())
    vertex_colls -= EXCLUDED_VERTEX_COLLECTIONS_BY_GRAPH.get(graph_name, set())
    edge_colls = set(ed["edge_collection"] for ed in g.edge_definitions())
    return vertex_colls, edge_colls


def prune_theme(base_theme_raw: dict, vertex_colls: Set[str], edge_colls: Set[str]) -> dict:
    """Return a deep copy of the theme with only collections present in the graph."""
    theme = copy.deepcopy(base_theme_raw)
    if "nodeConfigMap" in theme:
        theme["nodeConfigMap"] = {k: v for k, v in theme["nodeConfigMap"].items() if k in vertex_colls}
    if "edgeConfigMap" in theme:
        theme["edgeConfigMap"] = {k: v for k, v in theme["edgeConfigMap"].items() if k in edge_colls}
    return theme


def ensure_visualizer_shape(theme: dict) -> None:
    """Add required default fields that the Visualizer expects."""
    for node_cfg in theme.get("nodeConfigMap", {}).values():
        node_cfg.setdefault("rules", [])
        node_cfg.setdefault("hoverInfoAttributes", [])
    for edge_cfg in theme.get("edgeConfigMap", {}).values():
        edge_cfg.setdefault("rules", [])
        edge_cfg.setdefault("hoverInfoAttributes", [])
        edge_cfg.setdefault("arrowStyle", {"sourceArrowShape": "none", "targetArrowShape": "triangle"})
        edge_cfg.setdefault("labelStyle", {"color": "#1d2531"})


def _upsert_theme(theme_col, theme: dict) -> None:
    graph_name = theme["graphId"]
    existing = list(theme_col.find({"name": theme["name"], "graphId": graph_name}))
    if existing:
        theme["_key"] = existing[0]["_key"]
        theme["_id"] = existing[0]["_id"]
        # Preserve original creation timestamp
        theme["createdAt"] = existing[0].get("createdAt", theme["updatedAt"])
        theme_col.replace(theme, check_rev=False)
        print(f"  [Updated Theme]   {graph_name}::{theme['name']} "
              f"({len(theme.get('nodeConfigMap', {}))} nodes, "
              f"{len(theme.get('edgeConfigMap', {}))} edges)")
    else:
        theme["createdAt"] = theme["updatedAt"]
        theme_col.insert(theme)
        print(f"  [Installed Theme] {graph_name}::{theme['name']} "
              f"({len(theme.get('nodeConfigMap', {}))} nodes, "
              f"{len(theme.get('edgeConfigMap', {}))} edges)")


# ---------------------------------------------------------------------------
# Canvas action helpers
# ---------------------------------------------------------------------------

def _slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def _upsert_canvas_action(
    canvas_col,
    vp_act_col,
    vp_id: str,
    graph_name: str,
    name: str,
    description: str,
    query_text: str,
    bind_vars: dict,
    now: str,
) -> str:
    """Upsert a canvas action with a stable _key and link it to the viewpoint."""
    existing = list(canvas_col.find({"name": name, "graphId": graph_name}))
    if existing:
        # Keep lowest key; remove duplicates created before stable keys were enforced
        existing = sorted(existing, key=lambda d: d.get("_key", ""))
        for extra in existing[1:]:
            try:
                for edge in vp_act_col.find({"_to": extra["_id"]}):
                    vp_act_col.delete(edge["_key"])
                canvas_col.delete(extra["_key"])
            except Exception:
                pass
        doc = {
            "_key": existing[0]["_key"],
            "_id": existing[0]["_id"],
            "graphId": graph_name,
            "name": name,
            "description": description,
            "queryText": query_text,
            "bindVariables": bind_vars,
            "createdAt": existing[0].get("createdAt", now),
            "updatedAt": now,
        }
        canvas_col.replace(doc, check_rev=False)
        action_id = existing[0]["_id"]
    else:
        stable_key = _slugify(f"{graph_name}_{name}")
        doc = {
            "_key": stable_key,
            "graphId": graph_name,
            "name": name,
            "description": description,
            "queryText": query_text,
            "bindVariables": bind_vars,
            "createdAt": now,
            "updatedAt": now,
        }
        res = canvas_col.insert(doc)
        action_id = res["_id"]
        print(f"    [Installed action] {name} → {graph_name}")

    if not list(vp_act_col.find({"_from": vp_id, "_to": action_id})):
        vp_act_col.insert({"_from": vp_id, "_to": action_id, "createdAt": now, "updatedAt": now})

    return action_id


def install_canvas_actions(db, graph_name: str, vertex_colls: Set[str], edge_colls: Set[str]) -> None:
    """Install per-collection Expand actions plus a general 2-hop action."""
    ensure_collection(db, "_canvasActions")
    ensure_collection(db, "_viewpointActions", edge=True)

    canvas_col = db.collection("_canvasActions")
    vp_act_col = db.collection("_viewpointActions")
    vp_id = ensure_default_viewpoint(db, graph_name)
    now = datetime.utcnow().isoformat() + "Z"

    edge_list_str = ", ".join(sorted(edge_colls))
    with_clause = "WITH " + ", ".join(sorted(vertex_colls | edge_colls))

    # Remove stale "[Collection] Expand Relationships" actions for collections
    # no longer in the graph schema.
    expected_names = {f"[{v}] Expand Relationships" for v in vertex_colls}
    for a in list(canvas_col.find({"graphId": graph_name})):
        n = a.get("name", "")
        if n.startswith("[") and n.endswith("] Expand Relationships") and n not in expected_names:
            try:
                for edge in vp_act_col.find({"_to": a["_id"]}):
                    vp_act_col.delete(edge["_key"])
                canvas_col.delete(a["_key"])
            except Exception:
                pass

    # General 2-hop explorer (no collection filter)
    _upsert_canvas_action(
        canvas_col, vp_act_col, vp_id, graph_name,
        "Find 2-hop neighbors",
        "Expand 2 hops in any direction from selected nodes",
        f"""{with_clause}
FOR node IN @nodes
  FOR v, e IN 1..2 ANY node GRAPH "{graph_name}"
  LIMIT 100
  RETURN e""",
        {"nodes": []},
        now,
    )

    # Per-collection 1-hop expand
    for v_coll in sorted(vertex_colls):
        _upsert_canvas_action(
            canvas_col, vp_act_col, vp_id, graph_name,
            f"[{v_coll}] Expand Relationships",
            f"Expand 1-hop relationships for {v_coll} nodes",
            f"""{with_clause}
FOR node IN @nodes
  FILTER IS_SAME_COLLECTION("{v_coll}", node)
  FOR v, e, p IN 1..1 ANY node {edge_list_str}
  LIMIT 20
  RETURN p""",
            {"nodes": []},
            now,
        )

    print(f"    Installed {len(vertex_colls) + 1} canvas actions for {graph_name}")


# ---------------------------------------------------------------------------
# Saved queries (global editor) and Visualizer Queries panel
# ---------------------------------------------------------------------------

def _upsert_editor_saved_query(db, key: str, name: str, aql: str) -> None:
    """Upsert into _editor_saved_queries (global AQL editor sidebar).

    Sets both 'content' AND 'value' for cross-version compatibility.
    'queryText' is NOT used here — that field is for canvas actions only.
    """
    ensure_collection(db, "_editor_saved_queries")
    col = db.collection("_editor_saved_queries")
    now = datetime.utcnow().isoformat() + "Z"
    doc = {
        "_key": key,
        "name": name,
        "title": name,
        "content": aql,       # field read by newer ArangoDB UI versions
        "value": aql,         # field read by older ArangoDB UI versions
        "bindVariables": {},
        "databaseName": ARANGO_DATABASE,
        "updatedAt": now,
    }
    existing = list(col.find({"_key": key})) or list(col.find({"name": name}))
    if existing:
        doc["_key"] = existing[0]["_key"]
        doc["_id"] = existing[0]["_id"]
        doc["createdAt"] = existing[0].get("createdAt", now)
        col.replace(doc, check_rev=False)
        print(f"  [Updated editor query]    {name}")
    else:
        doc["createdAt"] = now
        col.insert(doc)
        print(f"  [Installed editor query]  {name}")


def _upsert_visualizer_query(db, graph_name: str, vp_id: str, key: str, name: str, aql: str) -> None:
    """Upsert into _queries and link via _viewpointQueries for the Visualizer Queries panel.

    'queryText' is used here (distinct from _editor_saved_queries which uses content/value).
    """
    ensure_collection(db, "_queries")
    ensure_collection(db, "_viewpointQueries", edge=True)

    col = db.collection("_queries")
    vp_q_col = db.collection("_viewpointQueries")
    now = datetime.utcnow().isoformat() + "Z"

    doc = {
        "_key": key,
        "name": name,
        "title": name,
        "description": "Load synthetic demo-scenario nodes onto the canvas",
        "graphId": graph_name,
        "queryText": aql,
        "bindVariables": {},
        "updatedAt": now,
    }
    existing = list(col.find({"_key": key})) or list(col.find({"name": name, "graphId": graph_name}))
    if existing:
        doc["_key"] = existing[0]["_key"]
        doc["_id"] = existing[0]["_id"]
        doc["createdAt"] = existing[0].get("createdAt", now)
        col.replace(doc, check_rev=False)
        query_id = existing[0]["_id"]
        print(f"  [Updated visualizer query] {name} ({graph_name})")
    else:
        doc["createdAt"] = now
        res = col.insert(doc)
        query_id = res["_id"]
        print(f"  [Installed visualizer query] {name} ({graph_name})")

    if not list(vp_q_col.find({"_from": vp_id, "_to": query_id})):
        vp_q_col.insert({"_from": vp_id, "_to": query_id, "createdAt": now, "updatedAt": now})


# ---------------------------------------------------------------------------
# Demo canvas action (canvas-level, not node-selection-based)
# ---------------------------------------------------------------------------

def install_demo_canvas_action(db, graph_name: str, vp_id: str) -> None:
    canvas_col = db.collection("_canvasActions")
    vp_act_col = db.collection("_viewpointActions")
    now = datetime.utcnow().isoformat() + "Z"
    _upsert_canvas_action(
        canvas_col, vp_act_col, vp_id, graph_name,
        "Load Demo Scenarios",
        "Bring all synthetic demo-scenario nodes onto the canvas",
        DEMO_SCENARIOS_QUERY,
        {},
        now,
    )


# ---------------------------------------------------------------------------
# Main installer
# ---------------------------------------------------------------------------

def install_themes() -> None:
    db = get_db()

    ensure_collection(db, "_graphThemeStore")
    theme_col = db.collection("_graphThemeStore")

    print(f"\nInstalling themes for database: {ARANGO_DATABASE}")
    print("=" * 80)

    themes_raw = []
    for path in THEME_FILES:
        if not os.path.exists(path):
            print(f"[WARN] Theme file not found: {path}")
            continue
        with open(path, encoding="utf-8") as f:
            themes_raw.append(json.load(f))

    for base_theme in themes_raw:
        print(f"\nProcessing theme: {base_theme.get('name')}")
        print("-" * 40)

        for graph_name in ["OntologyGraph"] + sorted(DATA_GRAPHS):
            vertex_colls, edge_colls = get_graph_schema(db, graph_name)
            if vertex_colls is None:
                print(f"  [SKIP] Graph '{graph_name}' does not exist")
                continue

            # OntologyGraph: only install the standard theme (renamed to "Ontology")
            if graph_name == "OntologyGraph":
                if base_theme.get("name") != "sentries_standard":
                    print(f"  [SKIP] '{base_theme.get('name')}' not relevant for OntologyGraph")
                    continue
                theme = prune_theme(base_theme, vertex_colls, edge_colls)
                theme["name"] = "Ontology"
                theme["description"] = "Standard Ontology visual configuration"
                theme["isDefault"] = True
            else:
                theme = prune_theme(base_theme, vertex_colls, edge_colls)
                # Make the risk heatmap the auto-applied default for data graphs
                theme["isDefault"] = (theme.get("name") == "sentries_risk_heatmap")

            theme["graphId"] = graph_name
            theme["updatedAt"] = datetime.utcnow().isoformat() + "Z"
            ensure_visualizer_shape(theme)
            _upsert_theme(theme_col, theme)

            # Canvas actions: per-collection expand + 2-hop explorer
            install_canvas_actions(db, graph_name, vertex_colls, edge_colls)

            # Demo canvas action + Queries-panel entry for data graphs only
            if graph_name in DATA_GRAPHS:
                vp_id = ensure_default_viewpoint(db, graph_name)
                install_demo_canvas_action(db, graph_name, vp_id)

    # AQL editor saved query (appears in the global editor sidebar)
    print("\nInstalling demo saved queries...")
    _upsert_editor_saved_query(
        db,
        key="risk_load_demo_scenarios",
        name="Load Demo Scenarios",
        aql=DEMO_SCENARIOS_QUERY,
    )

    # Graph Visualizer Queries panel (appears when browsing DataGraph / KnowledgeGraph)
    for graph_name in sorted(DATA_GRAPHS):
        if not db.has_graph(graph_name):
            continue
        vp_id = ensure_default_viewpoint(db, graph_name)
        _upsert_visualizer_query(
            db, graph_name, vp_id,
            key=f"risk_demo_scenarios_{_slugify(graph_name)}",
            name="Load Demo Scenarios",
            aql=DEMO_SCENARIOS_QUERY,
        )

    print("\n" + "=" * 80)
    print("Theme & Visualizer installation complete.")


if __name__ == "__main__":
    install_themes()
