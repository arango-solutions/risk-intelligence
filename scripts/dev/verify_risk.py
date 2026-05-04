import os
from dotenv import load_dotenv
from arango import ArangoClient

load_dotenv()

def verify_risk():
    client = ArangoClient(hosts=os.getenv('ARANGO_ENDPOINT'))
    db = client.db(os.getenv('ARANGO_DATABASE'), username=os.getenv('ARANGO_USERNAME'), password=os.getenv('ARANGO_PASSWORD'))
    
    collections = ['Person', 'Organization', 'Vessel', 'Aircraft']
    print("Risk Score Distribution Verification:")
    
    for coll in collections:
        if not db.has_collection(coll):
            continue
            
        count_direct = len(list(db.aql.execute(f"FOR d IN {coll} FILTER d.riskScore > 0 RETURN 1")))
        count_inferred = len(list(db.aql.execute(f"FOR d IN {coll} FILTER d.inferredRisk > 0 RETURN 1")))
        
        avg_q = f"FOR d IN {coll} FILTER d.inferredRisk > 0 COLLECT AGGREGATE a = AVERAGE(d.inferredRisk) RETURN a"
        avg_res = list(db.aql.execute(avg_q))
        avg = avg_res[0] if avg_res and avg_res[0] is not None else 0
        
        print(f"  {coll}:")
        print(f"    Direct Risk Nodes:   {count_direct}")
        print(f"    Inferred Risk Nodes: {count_inferred}")
        print(f"    Average Inferred:    {avg:.2f}")

if __name__ == "__main__":
    verify_risk()
