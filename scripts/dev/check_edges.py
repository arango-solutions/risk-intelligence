import os
from dotenv import load_dotenv
from arango import ArangoClient

load_dotenv()

def check_edges():
    client = ArangoClient(hosts=os.getenv('ARANGO_ENDPOINT'))
    db = client.db(os.getenv('ARANGO_DATABASE'), username=os.getenv('ARANGO_USERNAME'), password=os.getenv('ARANGO_PASSWORD'))
    
    edge_cols = ['type', 'domain', 'range', 'subClassOf']
    for col in edge_cols:
        if not db.has_collection(col):
            print(f"Collection {col} missing.")
            continue
            
        print(f"\nAnalyzing Edge Collection: {col}")
        
        sources = list(db.aql.execute(f"FOR doc IN @@col COLLECT s = PARSE_IDENTIFIER(doc._from).collection RETURN DISTINCT s", bind_vars={'@col': col}))
        print(f"  Sources: {sources}")
        
        targets = list(db.aql.execute(f"FOR doc IN @@col COLLECT t = PARSE_IDENTIFIER(doc._to).collection RETURN DISTINCT t", bind_vars={'@col': col}))
        # Filter out potential external URIs if they exist (though PARSE_IDENTIFIER might fail on them if not well-formed)
        print(f"  Targets: {targets}")

if __name__ == "__main__":
    check_edges()
