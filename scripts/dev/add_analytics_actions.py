import os
from dotenv import load_dotenv
from arango import ArangoClient
from datetime import datetime

# Load environment variables
load_dotenv()

ARANGO_ENDPOINT = os.getenv("ARANGO_ENDPOINT")
ARANGO_USERNAME = os.getenv("ARANGO_USERNAME", "root")
ARANGO_PASSWORD = os.getenv("ARANGO_PASSWORD")
ARANGO_DATABASE = os.getenv("ARANGO_DATABASE", "risk-management")

def add_analytics_actions():
    """Add analytics canvas actions for tracing to sanctioned entities."""
    client = ArangoClient(hosts=ARANGO_ENDPOINT)
    db = client.db(ARANGO_DATABASE, username=ARANGO_USERNAME, password=ARANGO_PASSWORD)
    
    print(f"\n{'='*80}")
    print("ADDING ANALYTICS CANVAS ACTIONS")
    print(f"{'='*80}\n")
    
    # Ensure collections exist
    for coll in ["_canvasActions", "_viewpoints", "_viewpointActions"]:
        if not db.has_collection(coll):
            if coll == "_viewpointActions":
                db.create_collection(coll, edge=True, system=True)
            else:
                db.create_collection(coll, system=True)
    
    canvas_col = db.collection("_canvasActions")
    vp_col = db.collection("_viewpoints")
    vp_act_col = db.collection("_viewpointActions")
    
    graphs = ["DataGraph", "KnowledgeGraph"]
    
    # Analytics actions for Person and Organization
    # These queries trace paths to entities with riskScore > 0 (sanctioned entities)
    analytics_actions = [
        {
            "entity_type": "Person",
            "name": "[Person] Trace to Sanctioned Entities",
            "description": "Trace paths from selected Person(s) to sanctioned entities (riskScore > 0) via ownership, leadership, or family ties",
            "query_template": """FOR node IN @nodes
  FOR v, e, p IN 1..3 ANY node
    owned_by, leader_of, family_member_of
    FILTER (v.riskScore || 0) > 0
    LIMIT 50
    RETURN p"""
        },
        {
            "entity_type": "Organization",
            "name": "[Organization] Trace to Sanctioned Entities",
            "description": "Trace paths from selected Organization(s) to sanctioned entities (riskScore > 0) via ownership, leadership, or operations",
            "query_template": """FOR node IN @nodes
  FOR v, e, p IN 1..3 ANY node
    owned_by, leader_of, operates
    FILTER (v.riskScore || 0) > 0
    LIMIT 50
    RETURN p"""
        }
    ]
    
    for graph_id in graphs:
        print(f"\n{'='*80}")
        print(f"PROCESSING {graph_id}")
        print(f"{'='*80}\n")
        
        # Get or create Default viewpoint
        default_vp = list(vp_col.find({"graphId": graph_id, "name": "Default"}))
        if not default_vp:
            # Try "Default - GraphName"
            default_vp = list(vp_col.find({"graphId": graph_id, "name": f"Default - {graph_id}"}))
        if not default_vp:
            # Create Default viewpoint
            now = datetime.utcnow().isoformat() + "Z"
            vp_doc = {
                "graphId": graph_id,
                "name": "Default",
                "description": f"Default viewpoint for {graph_id}",
                "createdAt": now,
                "updatedAt": now
            }
            res = vp_col.insert(vp_doc)
            default_vp = [vp_col.get(res["_key"])]
        
        vp_id = default_vp[0]["_id"]
        print(f"Using viewpoint: {default_vp[0].get('name')}")
        
        # Check which entity types exist in this graph
        if db.has_graph(graph_id):
            graph = db.graph(graph_id)
            vertex_colls = set(graph.vertex_collections())
            print(f"Vertex collections in {graph_id}: {sorted(vertex_colls)}")
        else:
            print(f"⚠️  Graph {graph_id} does not exist, skipping")
            continue
        
        # Add analytics actions for entities that exist in this graph
        for action_def in analytics_actions:
            entity_type = action_def["entity_type"]
            
            if entity_type not in vertex_colls:
                print(f"  ⏭️  Skipping {action_def['name']} - {entity_type} not in graph")
                continue
            
            action_name = action_def["name"]
            print(f"\n  Adding: {action_name}")
            
            # Check if action already exists
            existing = list(canvas_col.find({
                "graphId": graph_id,
                "name": action_name
            }))
            
            now = datetime.utcnow().isoformat() + "Z"
            # Use query_template and format with graph name if needed
            query_text = action_def["query_template"]
            
            action_doc = {
                "name": action_name,
                "description": action_def["description"],
                "queryText": query_text,
                "graphId": graph_id,
                "bindVariables": {
                    "nodes": ""
                },
                "updatedAt": now
            }
            
            if existing:
                # Update existing action
                action_id = existing[0]["_id"]
                action_doc["_key"] = existing[0]["_key"]
                action_doc["_id"] = existing[0]["_id"]
                canvas_col.replace(action_doc)
                print(f"    ✓ Updated existing action")
            else:
                # Create new action
                action_doc["createdAt"] = now
                res = canvas_col.insert(action_doc)
                action_id = res["_id"]
                print(f"    ✓ Created new action")
            
            # Link to viewpoint
            link_exists = list(vp_act_col.find({
                "_from": vp_id,
                "_to": action_id
            }))
            
            if not link_exists:
                vp_act_col.insert({
                    "_from": vp_id,
                    "_to": action_id,
                    "createdAt": now,
                    "updatedAt": now
                })
                print(f"    ✓ Linked to viewpoint")
            else:
                print(f"    ✓ Already linked to viewpoint")
    
    print(f"\n{'='*80}")
    print("ANALYTICS ACTIONS INSTALLATION COMPLETE")
    print(f"{'='*80}\n")
    
    # Summary
    print("Summary of installed analytics actions:")
    for graph_id in graphs:
        actions = list(canvas_col.find({
            "graphId": graph_id,
            "name": {"$like": "%Trace to Sanctioned%"}
        }))
        if actions:
            print(f"\n  {graph_id}:")
            for action in actions:
                print(f"    - {action.get('name')}")

if __name__ == "__main__":
    add_analytics_actions()
