"""
RETIRED — superseded by data/synthetic_parties.csv + data/synthetic_relationships.csv.

Synthetic demo nodes are now first-class data loaded via load_data.py.
Risk scores are propagated naturally by calculate_inferred_risk.py.

To reload synthetic data:
    python scripts/load_data.py
    python scripts/calculate_direct_risk.py
    python scripts/calculate_inferred_risk.py
"""

raise SystemExit(
    "add_demo_cruft.py is retired. "
    "Synthetic data now lives in data/synthetic_parties.csv and "
    "data/synthetic_relationships.csv. Run load_data.py instead."
)
