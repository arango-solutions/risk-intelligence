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
import uuid
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

# The single theme that should carry isDefault=true per graph. A theme marked
# default cannot be edited/saved in the Visualizer UI, so custom themes
# (sentries_standard, sentries_risk_heatmap) are always non-default. For data
# graphs we keep the Visualizer's built-in "Default" theme as the default.
DEFAULT_THEME_BY_GRAPH: Dict[str, str] = {
    "OntologyGraph": "Ontology",
    "DataGraph": "Default",
    "KnowledgeGraph": "Default",
}

# ---------------------------------------------------------------------------
# Demo query definitions
# Each entry: (key_suffix, display_name, aql)
# key_suffix is slugified and prefixed with "risk_" to form the _key in _queries.
# ---------------------------------------------------------------------------

def _scenario_union(scenario: str) -> str:
    """AQL UNION across all entity collections filtered by scenario label."""
    return (
        f'FOR doc IN UNION(\n'
        f'  (FOR d IN Person       FILTER d.dataSource == "Synthetic" AND d.scenario == "{scenario}" RETURN d),\n'
        f'  (FOR d IN Organization FILTER d.dataSource == "Synthetic" AND d.scenario == "{scenario}" RETURN d),\n'
        f'  (FOR d IN Vessel       FILTER d.dataSource == "Synthetic" AND d.scenario == "{scenario}" RETURN d),\n'
        f'  (FOR d IN Aircraft     FILTER d.dataSource == "Synthetic" AND d.scenario == "{scenario}" RETURN d)\n'
        f')\nRETURN doc'
    )


DEMO_SCENARIOS_QUERY = """\
FOR doc IN UNION(
  (FOR d IN Person       FILTER d.dataSource == "Synthetic" RETURN d),
  (FOR d IN Organization FILTER d.dataSource == "Synthetic" RETURN d),
  (FOR d IN Vessel       FILTER d.dataSource == "Synthetic" RETURN d),
  (FOR d IN Aircraft     FILTER d.dataSource == "Synthetic" RETURN d)
)
RETURN doc"""

# Ordered list of (key_suffix, display_name, aql) for the Visualizer Queries panel.
# The first entry is the "all scenarios" bulk loader; the rest are per-scenario.

# Scenario D: synthetic chain + NATIONAL IRANIAN TANKER COMPANY + 5 of its real subsidiaries
_SCENARIO_D_QUERY = """\
FOR doc IN UNION(
  (FOR d IN Organization FILTER d.dataSource == "Synthetic" AND d.scenario == "D" RETURN d),
  (FOR d IN Vessel       FILTER d.dataSource == "Synthetic" AND d.scenario == "D" RETURN d),
  (LET anchor = DOCUMENT("Organization/15117") RETURN anchor),
  (FOR e IN owned_by FILTER e._to == "Organization/15117"
   SORT RAND() LIMIT 5
   LET d = DOCUMENT(e._from) FILTER d != null RETURN d)
)
FILTER doc != null
RETURN doc"""

# Scenario A: synthetic network + FARC (the real SDN org Carlos leads)
_SCENARIO_A_QUERY = """\
FOR doc IN UNION(
  (FOR d IN Person       FILTER d.dataSource == "Synthetic" AND d.scenario == "A" RETURN d),
  (FOR d IN Organization FILTER d.dataSource == "Synthetic" AND d.scenario == "A" RETURN d),
  (FOR d IN Vessel       FILTER d.dataSource == "Synthetic" AND d.scenario == "A" RETURN d),
  (LET farc = DOCUMENT("Organization/33983") RETURN farc)
)
FILTER doc != null
RETURN doc"""

# Scenario E: synthetic chain + Sberbank + 5 of its real subsidiaries
_SCENARIO_E_QUERY = """\
FOR doc IN UNION(
  (FOR d IN Person       FILTER d.dataSource == "Synthetic" AND d.scenario == "E" RETURN d),
  (FOR d IN Organization FILTER d.dataSource == "Synthetic" AND d.scenario == "E" RETURN d),
  (LET sberbank = DOCUMENT("Organization/17018") RETURN sberbank),
  (FOR e IN owned_by FILTER e._to == "Organization/17018"
   SORT RAND() LIMIT 5
   LET d = DOCUMENT(e._from) FILTER d != null RETURN d)
)
FILTER doc != null
RETURN doc"""

# Clean portfolio: the generated non-sanctioned counterparties plus the few
# sanctioned anchors they are exposed to. Mostly green, with a handful of
# high/medium/low hotspots that demonstrate inferred-risk propagation.
_CLEAN_PORTFOLIO_QUERY = """\
FOR doc IN UNION(
  (FOR d IN Organization FILTER d.dataSource == "CleanPortfolio" RETURN d),
  (FOR d IN Person       FILTER d.dataSource == "CleanPortfolio" RETURN d),
  (FOR e IN owned_by FILTER e.dataSource == "CleanPortfolio"
     LET t = DOCUMENT(e._to) FILTER t != null AND t.dataSource != "CleanPortfolio" RETURN t),
  (FOR e IN family_member_of FILTER e.dataSource == "CleanPortfolio"
     LET t = DOCUMENT(e._to) FILTER t != null AND t.dataSource != "CleanPortfolio" RETURN t)
)
FILTER doc != null
RETURN doc"""

VISUALIZER_QUERIES = [
    (
        "all_scenarios",
        "All Demo Scenarios",
        DEMO_SCENARIOS_QUERY,
        "Load all synthetic demo entities onto the canvas",
    ),
    (
        "clean_portfolio",
        "Risk Portfolio (mostly clean)",
        _CLEAN_PORTFOLIO_QUERY,
        "Clean counterparty portfolio with a few sanctioned-exposure hotspots (high/medium/low gradient)",
    ),
    (
        "scenario_d_shell_game",
        "Demo D: Shell Game (3-hop)",
        _SCENARIO_D_QUERY,
        "Shell Game: Vetting Target → 3-hop chain → NATIONAL IRANIAN TANKER COMPANY (126 real subsidiaries)",
    ),
    (
        "scenario_e_proxy_link",
        "Demo E: Proxy Link (family)",
        _SCENARIO_E_QUERY,
        "Proxy Link: Vetting Target owned by Relative of Sberbank executive (41 real subsidiaries)",
    ),
    (
        "scenario_a_medina_network",
        "Demo A: Medina Network",
        _SCENARIO_A_QUERY,
        "Medina Network: Carlos Medina Ruiz leads FARC + corporate shells + family web",
    ),
    (
        "scenario_b_al_qasim",
        "Demo B: Al-Qasim Network",
        _scenario_union("B"),
        "Al-Qasim Network: second-degree associate chain from Scenario A",
    ),
    (
        "scenario_c_clean",
        "Demo C: Clean Counterparties",
        _scenario_union("C"),
        "Clean entities — no risk connections, expected riskLevel: low",
    ),
]


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
    """Add required default fields that the Visualizer expects.

    Also injects a fresh per-rule ``id`` (uuid4) into every attribute-based rule
    that uses the Visualizer's structured schema (``condition`` is an object).
    The Graph Visualizer keys rules by ``id``; missing/duplicate ids cause the
    Attribute-based editor to misbehave.
    """
    # Drop JSON helper/comment keys (prefixed with "_") that are not part of the
    # theme document the Visualizer reads.
    for k in [k for k in theme if k.startswith("_")]:
        del theme[k]

    for node_cfg in theme.get("nodeConfigMap", {}).values():
        node_cfg.setdefault("rules", [])
        node_cfg.setdefault("hoverInfoAttributes", [])
        for rule in node_cfg.get("rules", []):
            if isinstance(rule.get("condition"), dict):
                rule["id"] = str(uuid.uuid4())
    for edge_cfg in theme.get("edgeConfigMap", {}).values():
        edge_cfg.setdefault("rules", [])
        edge_cfg.setdefault("hoverInfoAttributes", [])
        edge_cfg.setdefault("arrowStyle", {"sourceArrowShape": "none", "targetArrowShape": "triangle"})
        edge_cfg.setdefault("labelStyle", {"color": "#1d2531"})
        for rule in edge_cfg.get("rules", []):
            if isinstance(rule.get("condition"), dict):
                rule["id"] = str(uuid.uuid4())


def enforce_single_default(theme_col, graph_name: str) -> None:
    """Ensure exactly one isDefault=true theme per graph.

    A theme with isDefault=true cannot be saved/edited in the Visualizer UI, so
    only the designated default (see DEFAULT_THEME_BY_GRAPH) is flagged true and
    every other theme for the graph is forced to false. If the designated default
    theme doesn't exist yet (e.g. the Visualizer hasn't auto-created "Default" for
    a brand-new graph), we still clear all custom defaults and warn.
    """
    default_name = DEFAULT_THEME_BY_GRAPH.get(graph_name)
    if not default_name:
        return
    themes = list(theme_col.find({"graphId": graph_name}))
    found = False
    for t in themes:
        want = (t.get("name") == default_name)
        found = found or want
        if t.get("isDefault") != want:
            theme_col.update({"_key": t["_key"], "isDefault": want}, check_rev=False)
            print(f"    [isDefault] {graph_name}::{t.get('name')} -> {want}")
    if not found:
        print(f"    [WARN] {graph_name}: no '{default_name}' theme present; custom "
              f"themes set non-default. The Visualizer creates '{default_name}' on first open.")


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


def install_canvas_actions(db, graph_name: str, vertex_colls: Set[str], edge_colls: Set[str],
                           include_trace: bool = False) -> None:
    """Install per-collection Expand actions plus a general 2-hop action.

    When include_trace is True (data graphs only), also install a
    'Trace to sanctioned source' action that returns the shortest path(s)
    from the selected node(s) to the nearest highly sanctioned entity.
    """
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

    # Trace to the nearest highly sanctioned entity (data graphs only).
    # PRUNE + bfs returns the shortest path that reaches a sanctioned node and
    # stops there, so the result is the nearest exposure rather than deeper
    # noise. RETURN p renders the full path (vertices + edges) for an
    # explainable, hop-by-hop justification.
    if include_trace:
        _upsert_canvas_action(
            canvas_col, vp_act_col, vp_id, graph_name,
            "Trace to sanctioned source",
            "Shortest path(s) from the selected node(s) to the nearest highly "
            "sanctioned entity (riskScore >= 0.9)",
            f"""{with_clause}
FOR node IN @nodes
  FOR v, e, p IN 1..4 ANY node GRAPH "{graph_name}"
    PRUNE (v.riskScore || 0) >= 0.9
    OPTIONS {{ uniqueVertices: "path", bfs: true }}
    FILTER (v.riskScore || 0) >= 0.9
    LIMIT 50
    RETURN p""",
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

    general_count = 2 if include_trace else 1
    print(f"    Installed {len(vertex_colls) + general_count} canvas actions for {graph_name}")


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


def _upsert_visualizer_query(
    db, graph_name: str, vp_id: str, key: str, name: str, aql: str,
    description: str = "",
) -> None:
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
        "description": description or name,
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
        print(f"  [Updated visualizer query]   {name} ({graph_name})")
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
                # Keep the Visualizer's built-in "Default" theme as the auto-applied
                # default for data graphs; custom themes are opt-in via the Legend.
                # A theme marked isDefault=true cannot be saved/edited in the UI, so
                # never flag sentries_risk_heatmap / sentries_standard as default.
                theme["isDefault"] = False

            theme["graphId"] = graph_name
            theme["updatedAt"] = datetime.utcnow().isoformat() + "Z"
            ensure_visualizer_shape(theme)
            _upsert_theme(theme_col, theme)

            # Canvas actions: per-collection expand + 2-hop explorer (+ trace
            # to sanctioned source on data graphs, which carry riskScore)
            install_canvas_actions(db, graph_name, vertex_colls, edge_colls,
                                   include_trace=graph_name in DATA_GRAPHS)

            # Demo canvas action + Queries-panel entry for data graphs only
            if graph_name in DATA_GRAPHS:
                vp_id = ensure_default_viewpoint(db, graph_name)
                install_demo_canvas_action(db, graph_name, vp_id)

    # Enforce a single, editable default theme per graph (authoritative pass).
    print("\nEnforcing single default theme per graph...")
    for graph_name in TARGET_GRAPHS:
        if db.has_graph(graph_name):
            enforce_single_default(theme_col, graph_name)

    # AQL editor saved query (global Query Editor sidebar — bulk loader only)
    print("\nInstalling demo saved queries...")
    _upsert_editor_saved_query(
        db,
        key="risk_load_demo_scenarios",
        name="All Demo Scenarios",
        aql=DEMO_SCENARIOS_QUERY,
    )

    # Graph Visualizer Queries panel — one entry per scenario for both data graphs
    for graph_name in sorted(DATA_GRAPHS):
        if not db.has_graph(graph_name):
            continue
        vp_id = ensure_default_viewpoint(db, graph_name)
        for suffix, display_name, aql, desc in VISUALIZER_QUERIES:
            _upsert_visualizer_query(
                db, graph_name, vp_id,
                key=f"risk_{suffix}_{_slugify(graph_name)}",
                name=display_name,
                aql=aql,
                description=desc,
            )

    print("\n" + "=" * 80)
    print("Theme & Visualizer installation complete.")


if __name__ == "__main__":
    install_themes()
