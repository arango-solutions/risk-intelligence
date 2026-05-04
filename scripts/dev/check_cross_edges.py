import os
from dotenv import load_dotenv
from arango import ArangoClient

load_dotenv()

def check_cross_divide_edges():
    client = ArangoClient(hosts=os.getenv('ARANGO_ENDPOINT'))
    db = client.db(os.getenv('ARANGO_DATABASE'), username=os.getenv('ARANGO_USERNAME'), password=os.getenv('ARANGO_PASSWORD'))
    
    ontology_colls = ['Class', 'Property', 'ObjectProperty', 'Ontology']
    data_colls = ['Person', 'Organization', 'Vessel', 'Aircraft']
    
    all_edge_colls = [c['name'] for c in db.collections() if c['type'] == 'edge' and not c['name'].startswith('_')]
    
    print("Checking for cross-divide edges...")
    for col in all_edge_colls:
        # Check edges from Data to Ontology
        data_ids = ", ".join([f"'{c}'" for c in data_colls])
        ont_ids = ", ".join([f"'{c}'" for c in ontology_colls])
        
        aql = f"""
        FOR d IN {col}
            LET f_coll = PARSE_IDENTIFIER(d._from).collection
            LET t_coll = PARSE_IDENTIFIER(d._to).collection
            FILTER (f_coll IN [{data_ids}] AND t_coll IN [{ont_ids}])
                OR (f_coll IN [{ont_ids}] AND t_coll IN [{data_ids}])
            LIMIT 5
            RETURN {{from: d._from, to: d._to, type: '{col}'}}
        """
        cross = list(db.aql.execute(aql))
        if cross:
            print(f"Found cross edges in {col}:")
            for c in cross:
                print(f"  {c['from']} -> {c['to']}")
        else:
            print(f"  No cross edges in {col}.")

if __name__ == "__main__":
    check_cross_divide_edges()
