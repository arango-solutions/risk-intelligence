import os
import re
from arango import ArangoClient

# Load environment variables manually
def load_env():
    if os.path.exists('.env'):
        with open('.env') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                match = re.match(r'^\s*([\w.-]+)\s*=\s*(.*)\s*$', line)
                if match:
                    key = match.group(1)
                    value = match.group(2).strip()
                    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
                        value = value[1:-1]
                    os.environ[key] = value

def run_propagation_iteration(db, colls):
    # Unified propagation query for efficiency
    # Pass 1: Ownership
    for c in colls:
        if db.has_collection(c):
            db.aql.execute(f"""
                FOR e IN owned_by 
                FILTER IS_SAME_COLLECTION('{c}', e._from) 
                LET o = DOCUMENT(e._to) 
                FILTER o != null AND (o.inferredRisk || 0) > 0 
                LET nr = o.inferredRisk * 1.0 
                LET target = DOCUMENT(e._from)
                FILTER nr > (target.inferredRisk || 0) 
                UPDATE target WITH {{ inferredRisk: nr }} IN {c}
            """)
    
    # Pass 2: Leadership
    if db.has_collection('leader_of'):
        db.aql.execute("""
            FOR e IN leader_of 
            LET l = DOCUMENT(e._from) 
            FILTER l != null AND (l.inferredRisk || 0) > 0 
            LET nr = l.inferredRisk * 0.8 
            LET ent = DOCUMENT(e._to) 
            FILTER ent != null AND nr > (ent.inferredRisk || 0) 
            UPDATE ent WITH { inferredRisk: nr } IN Organization
        """)
    
    # Pass 3: Family (Two steps for symmetry)
    if db.has_collection('family_member_of'):
        db.aql.execute("""
            FOR e IN family_member_of 
            LET p1 = DOCUMENT(e._from) 
            LET p2 = DOCUMENT(e._to) 
            FILTER p1 != null AND (p1.inferredRisk || 0) > 0 
            LET nr = p1.inferredRisk * 0.5 
            FILTER p2 != null AND nr > (p2.inferredRisk || 0) 
            UPDATE p2 WITH { inferredRisk: nr } IN Person
        """)
        db.aql.execute("""
            FOR e IN family_member_of 
            LET p1 = DOCUMENT(e._from) 
            LET p2 = DOCUMENT(e._to) 
            FILTER p2 != null AND (p2.inferredRisk || 0) > 0 
            LET nr = p2.inferredRisk * 0.5 
            FILTER p1 != null AND nr > (p1.inferredRisk || 0) 
            UPDATE p1 WITH { inferredRisk: nr } IN Person
        """)

    # Pass 4: Operates (bidirectional, weight 0.9)
    # Risk flows both ways: a high-risk operator taints the vessel/asset and vice-versa.
    # We iterate over all (from_coll, to_coll) pairs to handle cross-collection edges
    # (e.g. Organization operates Vessel).
    if db.has_collection('operates'):
        for from_c in colls:
            if not db.has_collection(from_c):
                continue
            for to_c in colls:
                if not db.has_collection(to_c):
                    continue
                # operator (from_c) → operated entity (to_c)
                db.aql.execute(f"""
                    FOR e IN operates
                    FILTER IS_SAME_COLLECTION('{from_c}', e._from)
                    FILTER IS_SAME_COLLECTION('{to_c}', e._to)
                    LET op = DOCUMENT(e._from)
                    FILTER op != null AND (op.inferredRisk || 0) > 0
                    LET nr = op.inferredRisk * 0.9
                    LET ent = DOCUMENT(e._to)
                    FILTER ent != null AND nr > (ent.inferredRisk || 0)
                    UPDATE ent WITH {{ inferredRisk: nr }} IN {to_c}
                """)
                # operated entity (to_c) → operator (from_c)
                db.aql.execute(f"""
                    FOR e IN operates
                    FILTER IS_SAME_COLLECTION('{from_c}', e._from)
                    FILTER IS_SAME_COLLECTION('{to_c}', e._to)
                    LET ent = DOCUMENT(e._to)
                    FILTER ent != null AND (ent.inferredRisk || 0) > 0
                    LET nr = ent.inferredRisk * 0.9
                    LET op = DOCUMENT(e._from)
                    FILTER op != null AND nr > (op.inferredRisk || 0)
                    UPDATE op WITH {{ inferredRisk: nr }} IN {from_c}
                """)

if __name__ == "__main__":
    load_env()
    endpoint = os.environ.get('ARANGO_ENDPOINT') or os.environ.get('ARANGO_URL')
    username = os.environ.get('ARANGO_USERNAME') or os.environ.get('ARANGO_USER', 'root')
    password = os.environ.get('ARANGO_PASSWORD')
    database = os.environ.get('ARANGO_DATABASE', 'risk-intelligence')

    client = ArangoClient(hosts=endpoint)
    db = client.db(database, username=username, password=password)
    
    colls = ["Person", "Organization", "Vessel", "Aircraft"]
    
    print("Initializing inferredRisk from direct riskScore...")
    for c in colls:
        if db.has_collection(c):
            db.aql.execute(f"FOR d IN {c} UPDATE d WITH {{ inferredRisk: d.riskScore || 0 }} IN {c}")
    
    iterations = 5
    for i in range(1, iterations + 1):
        print(f"Propagating iteration {i}/{iterations}...")
        run_propagation_iteration(db, colls)

    # Write a discrete riskLevel string so the Visualizer can use simple
    # equality conditions (universally supported across all Visualizer versions)
    # rather than numeric comparisons which require a newer Visualizer build.
    print("Writing riskLevel attribute...")
    for c in colls:
        if db.has_collection(c):
            db.aql.execute(f"""
                FOR d IN {c}
                    LET ir = d.inferredRisk || 0
                    LET lvl = ir >= 0.8 ? 'high' : (ir >= 0.3 ? 'medium' : 'low')
                    UPDATE d WITH {{ riskLevel: lvl }} IN {c}
            """)

    print("Inferred risk propagation complete.")
