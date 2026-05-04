import os
import json
from dotenv import load_dotenv
from arango import ArangoClient

# Load environment variables
load_dotenv()

ARANGO_ENDPOINT = os.getenv("ARANGO_ENDPOINT")
ARANGO_USERNAME = os.getenv("ARANGO_USERNAME", "root")
ARANGO_PASSWORD = os.getenv("ARANGO_PASSWORD")
ARANGO_DATABASE = os.getenv("ARANGO_DATABASE", "risk-management")

def check_theme_structure():
    """Check if theme structure matches what ArangoDB Visualizer expects."""
    client = ArangoClient(hosts=ARANGO_ENDPOINT)
    
    # Check working database
    themes_db = client.db("themes", username=ARANGO_USERNAME, password=ARANGO_PASSWORD)
    working_theme = list(themes_db.collection("_graphThemeStore").find({
        "graphId": "FOAF-Graph",
        "name": "FOAF"
    }))[0]
    
    # Check problem database
    risk_db = client.db(ARANGO_DATABASE, username=ARANGO_USERNAME, password=ARANGO_PASSWORD)
    problem_theme = list(risk_db.collection("_graphThemeStore").find({
        "graphId": "KnowledgeGraph",
        "name": "sentries_standard"
    }))[0]
    
    print(f"\n{'='*80}")
    print("CHECKING THEME STRUCTURE FOR VISUALIZER COMPATIBILITY")
    print(f"{'='*80}\n")
    
    # Check if nodeConfigMap structure is correct
    print("Working Theme - Person nodeConfigMap keys:")
    working_person = working_theme.get("nodeConfigMap", {}).get("Person", {})
    print(f"  {list(working_person.keys())}")
    
    print("\nProblem Theme - Person nodeConfigMap keys:")
    problem_person = problem_theme.get("nodeConfigMap", {}).get("Person", {})
    print(f"  {list(problem_person.keys())}")
    
    # Check if background is properly structured
    print("\n\nBackground Structure Check:")
    print("-" * 80)
    
    working_bg = working_person.get("background", {})
    problem_bg = problem_person.get("background", {})
    
    print(f"Working - background type: {type(working_bg)}")
    print(f"Working - background keys: {list(working_bg.keys()) if isinstance(working_bg, dict) else 'N/A'}")
    print(f"Working - background: {working_bg}")
    
    print(f"\nProblem - background type: {type(problem_bg)}")
    print(f"Problem - background keys: {list(problem_bg.keys()) if isinstance(problem_bg, dict) else 'N/A'}")
    print(f"Problem - background: {problem_bg}")
    
    # Check if iconName is directly accessible
    print("\n\nIcon Name Access:")
    print("-" * 80)
    print(f"Working - iconName: {working_bg.get('iconName')}")
    print(f"Problem - iconName: {problem_bg.get('iconName')}")
    
    # Check if there are any extra fields that might interfere
    print("\n\nFull Theme Document Keys:")
    print("-" * 80)
    working_keys = set(working_theme.keys())
    problem_keys = set(problem_theme.keys())
    
    print(f"Working theme keys: {sorted(working_keys)}")
    print(f"Problem theme keys: {sorted(problem_keys)}")
    
    extra_in_problem = problem_keys - working_keys
    if extra_in_problem:
        print(f"\n⚠️  Extra keys in problem theme: {extra_in_problem}")
        for key in extra_in_problem:
            print(f"  {key}: {type(problem_theme[key]).__name__}")

if __name__ == "__main__":
    check_theme_structure()
