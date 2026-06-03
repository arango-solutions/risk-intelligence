import os
import lxml.etree as etree
from dotenv import load_dotenv
from arango import ArangoClient

# Load environment variables
load_dotenv()

ARANGO_ENDPOINT = os.getenv("ARANGO_ENDPOINT")
ARANGO_USERNAME = os.getenv("ARANGO_USERNAME", "root")
ARANGO_PASSWORD = os.getenv("ARANGO_PASSWORD")
ARANGO_DATABASE = os.getenv("ARANGO_DATABASE", "risk-intelligence")

# File paths
XML_PATH = "data/SDN_ADVANCED.XML"

# Weight Mappings based on ListID
WEIGHTS = {
    "1550": 1.0,   # SDN List (Critical)
    "91512": 0.7,  # Consolidated List (High)
    "91507": 0.5,  # SSI List (Medium)
    "91243": 0.3   # Non-SDN Palestinian (Low)
}

# Human-readable source list per ListID. Recorded on each entity as
# `sanctionsSources` so a trace can report WHICH list flagged the target.
# This is also the seam for future jurisdictions (EU/UN/OFSI): add their
# parsed entries to source_map and they appear here with no downstream change.
LIST_NAMES = {
    "1550": "OFAC SDN",
    "91512": "OFAC Consolidated",
    "91507": "OFAC SSI",
    "91243": "OFAC Non-SDN Palestinian",
}

def calculate_direct_risk():
    client = ArangoClient(hosts=ARANGO_ENDPOINT)
    db = client.db(ARANGO_DATABASE, username=ARANGO_USERNAME, password=ARANGO_PASSWORD)
    
    print(f"Parsing {XML_PATH} for risk scoring...")
    
    # Store ProfileID -> Score, and ProfileID -> set of source list names
    risk_map = {}
    source_map = {}
    
    # Iterative parse for SanctionsEntry
    context = etree.iterparse(XML_PATH, events=('end',), tag='{*}SanctionsEntry')
    
    count = 0
    for event, elem in context:
        profile_id = str(elem.get("ProfileID"))
        list_id = str(elem.get("ListID"))
        
        # Determine score (default to 0.1 for trace visibility if not in weight map)
        score = WEIGHTS.get(list_id, 0.1)
        
        # If multiple entries for one profile, take the highest risk
        if profile_id not in risk_map or score > risk_map[profile_id]:
            risk_map[profile_id] = score

        # Record every source list this profile appears on (a profile can be on
        # more than one list).
        source_map.setdefault(profile_id, set()).add(LIST_NAMES.get(list_id, "OFAC Other"))
            
        count += 1
        elem.clear()
        while elem.getprevious() is not None:
            del elem.getparent()[0]
            
    print(f"Found {len(risk_map)} unique profiles with direct risk metadata.")

    # Apply updates to ArangoDB collections
    collections = ["Person", "Organization", "Vessel", "Aircraft"]
    total_updated = 0
    
    for coll_name in collections:
        if not db.has_collection(coll_name):
            continue
            
        print(f"Updating risk scores for {coll_name}...")
        
        # Batch updates for efficiency
        batch = []
        # Fetch existing keys to only update what exists
        cursor = db.aql.execute(f"FOR d IN {coll_name} RETURN d._key")
        existing_keys = set(cursor)
        
        for pid, score in risk_map.items():
            # Never overwrite riskScore on synthetic parties — they self-declare it at load time
            if pid.startswith("SYN-"):
                continue
            if pid in existing_keys:
                batch.append({
                    "_key": pid,
                    "riskScore": score,
                    "sanctionsSources": sorted(source_map.get(pid, [])),
                })
                
                if len(batch) >= 1000:
                    db.collection(coll_name).update_many(batch)
                    total_updated += len(batch)
                    batch = []
                    
        # Final batch
        if batch:
            db.collection(coll_name).update_many(batch)
            total_updated += len(batch)

    print(f"Successfully updated {total_updated} entities with direct risk scores.")

if __name__ == "__main__":
    calculate_direct_risk()
