import os
from dotenv import load_dotenv
from arango import ArangoClient

load_dotenv()

def cleanup_viewpoints():
    client = ArangoClient(hosts=os.getenv('ARANGO_ENDPOINT'))
    db = client.db(os.getenv('ARANGO_DATABASE'), username=os.getenv('ARANGO_USERNAME'), password=os.getenv('ARANGO_PASSWORD'))
    
    viewpoints_col = db.collection('_viewpoints')
    active_graphs = [g['name'] for g in db.graphs()]
    
    print(f"Active Graphs: {active_graphs}")
    
    for vp in viewpoints_col.all():
        gid = vp.get('graphId')
        
        # Delete if graph no longer exists
        if gid not in active_graphs and gid != '_viewpointGraph':
            print(f"Deleting orphaned viewpoint: {vp['_key']} (Graph: {gid})")
            viewpoints_col.delete(vp['_key'])
            continue
            
        # Rename "Default" for better clarity
        if vp.get('name') == 'Default' and gid != '_viewpointGraph':
            new_name = f"Default - {gid}"
            print(f"Renaming viewpoint {vp['_key']} for {gid} to '{new_name}'")
            viewpoints_col.update({'_key': vp['_key'], 'name': new_name})
            
    # Ensure KnowledgeGraph has a viewpoint if it exists
    if 'KnowledgeGraph' in active_graphs:
        exists = list(viewpoints_col.find({'graphId': 'KnowledgeGraph'}))
        if not exists:
            new_vp = {
                'graphId': 'KnowledgeGraph',
                'name': 'Default - KnowledgeGraph',
                'description': 'Default viewpoint for KnowledgeGraph'
            }
            viewpoints_col.insert(new_vp)
            print("Created default viewpoint for KnowledgeGraph")

if __name__ == "__main__":
    cleanup_viewpoints()
