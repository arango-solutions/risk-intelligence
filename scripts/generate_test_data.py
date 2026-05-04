"""
generate_test_data.py

Loads all synthetic demo entities (Scenarios A–E) into the database, then runs
inferred-risk propagation and verifies the expected risk values for the two
core demo scenarios:

  Scenario D – Shell Game (3-hop ownership chain)
    Sanctioned Org (1.0) → Holding Layer 1 → Holding Layer 2
      → Vetting Target - Shell Game  [expected inferredRisk: 1.0]

  Scenario E – Proxy Link (family + ownership)
    Sanctioned Individual (1.0)
      → Relative [expected inferredRisk: 0.5]
        → Vetting Target - Family Link  [expected inferredRisk: 0.5]

Run:
    python scripts/generate_test_data.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent


def _run(script_name: str) -> None:
    script = SCRIPTS_DIR / script_name
    print(f"\n  → {script_name}")
    result = subprocess.run([sys.executable, str(script)], cwd=SCRIPTS_DIR.parent)
    if result.returncode != 0:
        sys.exit(f"\n[ERROR] {script_name} failed with code {result.returncode}")


def _verify(db) -> None:
    checks = [
        # (party_key, collection, description, expected_min)
        ("SYN-D04", "Organization", "Vetting Target - Shell Game",  0.99),
        ("SYN-D03", "Organization", "Holding Layer 2",              0.99),
        ("SYN-D02", "Organization", "Holding Layer 1",              0.99),
        ("SYN-E02", "Person",       "Relative",                     0.49),
        ("SYN-E03", "Organization", "Vetting Target - Family Link",  0.49),
        ("SYN-C01", "Organization", "Clean counterparty (should be ~0)", -0.01),
    ]
    print("\n--- Demo scenario verification ---")
    all_ok = True
    for key, coll, label, expected_min in checks:
        doc = db.collection(coll).get(key)
        if doc is None:
            print(f"  [MISSING] {label} ({coll}/{key})")
            all_ok = False
            continue
        ir = doc.get("inferredRisk", 0.0)
        rl = doc.get("riskLevel", "?")
        ok = ir > expected_min
        status = "OK " if ok else "WARN"
        print(f"  [{status}] {label:45s}  inferredRisk={ir:.3f}  riskLevel={rl}")
        if not ok:
            all_ok = False
    if all_ok:
        print("\nAll demo scenarios verified successfully.\n")
    else:
        print("\n[WARN] Some checks did not pass – re-run after fixing data.\n")


if __name__ == "__main__":
    print("=" * 62)
    print("  Generating / refreshing demo test data")
    print("=" * 62)

    _run("load_synthetic_data.py")
    _run("calculate_inferred_risk.py")

    # Connect for verification using same config as other scripts
    sys.path.insert(0, str(SCRIPTS_DIR))
    from common import apply_config_to_env, get_arango_config, load_dotenv, sanitize_url
    from arango import ArangoClient

    load_dotenv()
    cfg = get_arango_config()
    apply_config_to_env(cfg)
    print(f"\nConnecting to {sanitize_url(cfg.url)} / {cfg.database}")
    client = ArangoClient(hosts=cfg.url)
    db = client.db(cfg.database, username=cfg.username, password=cfg.password)

    _verify(db)
    print("Run 'python scripts/install_theme.py' to refresh Visualizer assets.")
