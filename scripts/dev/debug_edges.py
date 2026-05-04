import os
from dotenv import load_dotenv
from arango import ArangoClient

load_dotenv()

def debug_dangling_edges():
    client = ArangoClient(hosts=os.getenv('ARANGO_ENDPOINT'))
    db = client.db(os.getenv('ARANGO_DATABASE'), username=os.getenv('ARANGO_USERNAME'), password=os.getenv('ARANGO_PASSWORD'))
    
    graphs = list(db.graphs())
    print(f"Graphs: {[g['name'] for g in graphs]}")
    
    edge_colls = [c['name'] for c in db.collections() if c['type'] == 'edge' and not c['name'].startswith('_')]
    print(f"Edge Collections: {edge_colls}")
    
    vertex_colls = [c['name'] for c in db.collections() if c['type'] == 'document' and not c['name'].startswith('_')]
    print(f"Vertex Collections: {vertex_colls}")

    print("\n--- Graph Definition Check ---")
    for g_info in graphs:
        g = db.graph(g_info['name'])
        defs = g.edge_definitions()
        print(f"\nGraph: {g_info['name']}")
        included_edges = [d['edge_collection'] for d in defs]
        missing_edges = [e for e in edge_colls if e not in included_edges]
        print(f"  Missing Edge Collections: {missing_edges}")
        
        for d in defs:
            print(f"  Edge: {d['edge_collection']}")
            print(f"    From: {d['from_vertex_collections']}")
            print(f"    To:   {d['to_vertex_collections']}")

    print("\n--- Dangling Edge Check (Database level) ---")
    for ec in edge_colls:
        count = db.collection(ec).count()
        if count == 0: continue
        
        # Check targets
        bad_targets = list(db.aql.execute(f"FOR d IN @@ec LET t = DOCUMENT(d._to) FILTER t == null LIMIT 5 RETURN d._to", bind_vars={'@ec': ec}))
        if bad_targets:
            print(f"  [BAD] Collection {ec} has edges pointing to non-existent vertices: {bad_targets}")
        
        # Check sources
        bad_sources = list(db.aql.execute(f"FOR d IN @@ec LET s = DOCUMENT(d._from) FILTER s == null LIMIT 5 RETURN d._from", bind_vars={'@ec': ec}))
        if bad_sources:
            print(f"  [BAD] Collection {ec} has edges originating from non-existent vertices: {bad_sources}")

    print("\n--- Person-Specific Check ---")
    data_graph_edges = [d['edge_collection'] for d in db.graph('DataGraph').edge_definitions()]
    # Check all edge collections for vertices that might be "dangling"
    for ec in edge_colls:
        if db.collection(ec).count() == 0: continue
        
        # Check for edges involving Person
        q = f"FOR d IN @@ec FILTER CONTAINS(d._from, 'Person/') OR CONTAINS(d._to, 'Person/') LIMIT 5 RETURN d"
        p_edges = list(db.aql.execute(q, bind_vars={'@ec': ec}))
        if p_edges:
            print(f"  Collection {ec} has edges involving Person (e.g., {p_edges[0]['_from']} -> {p_edges[0]['_to']})")
            if ec not in data_graph_edges and ec not in ['type']:
                print(f"    [WARNING] This collection is NOT in DataGraph. This could cause dangling edges if Person nodes are shown.")

    # Check for edges pointing to UnknownResource
    for ec in edge_colls:
        u_count = db.aql.execute(f"FOR d IN @@ec FILTER CONTAINS(d._from, 'UnknownResource') OR CONTAINS(d._to, 'UnknownResource') RETURN 1", bind_vars={'@ec': ec}).count() or 0
        if u_count > 0:
            print(f"  [INFO] Collection {ec} has {u_count} connections to UnknownResource.")

if __name__ == "__main__":
    debug_dangling_edges()
