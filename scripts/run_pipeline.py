#!/usr/bin/env python3
"""
Master pipeline runner for risk-intelligence.

Runs all pipeline stages in order:
  1. load_data          – ingest ontology, real OFAC parties/relationships, synthetic fixtures
  2. calculate_direct_risk  – score entities from OFAC XML
  3. calculate_inferred_risk – propagate risk through the graph
  4. install_theme       – push themes and canvas actions to the Visualizer

Usage:
    python scripts/run_pipeline.py              # full pipeline
    python scripts/run_pipeline.py --skip-data  # re-score + re-theme an existing dataset
    python scripts/run_pipeline.py --only-themes
"""

import argparse
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent

# Ordered pipeline stages: (script_stem, human-readable description)
STAGES = [
    ("load_data",              "Load ontology, parties & synthetic fixtures"),
    ("calculate_direct_risk",  "Calculate direct risk scores from OFAC data"),
    ("calculate_inferred_risk","Propagate inferred risk through the graph"),
    ("install_theme",          "Install Visualizer themes & canvas actions"),
]


def _run(script_stem: str, description: str) -> bool:
    script = SCRIPTS_DIR / f"{script_stem}.py"
    print(f"\n{'='*62}")
    print(f"  STEP: {description}")
    print(f"  script: {script.name}")
    print(f"{'='*62}")
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=SCRIPTS_DIR.parent,
    )
    if result.returncode != 0:
        print(
            f"\n[ERROR] {script.name} exited with code {result.returncode}",
            file=sys.stderr,
        )
        return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the risk-intelligence data pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--skip-data",
        action="store_true",
        help="Skip load_data (assume collections already populated)",
    )
    parser.add_argument(
        "--skip-risk",
        action="store_true",
        help="Skip both risk-calculation steps",
    )
    parser.add_argument(
        "--skip-themes",
        action="store_true",
        help="Skip install_theme",
    )
    parser.add_argument(
        "--only-themes",
        action="store_true",
        help="Run install_theme only (shorthand for --skip-data --skip-risk)",
    )
    args = parser.parse_args()

    if args.only_themes:
        args.skip_data = True
        args.skip_risk = True

    selected: list[tuple[str, str]] = []
    if not args.skip_data:
        selected.append(STAGES[0])
    if not args.skip_risk:
        selected += STAGES[1:3]
    if not args.skip_themes:
        selected.append(STAGES[3])

    if not selected:
        print("No stages selected — all stages were skipped. Use --help to see options.")
        sys.exit(0)

    total = len(selected)
    print(f"\nPipeline: {total} stage(s) selected")

    for i, (stem, desc) in enumerate(selected, 1):
        print(f"\n[{i}/{total}]", end="")
        if not _run(stem, desc):
            print(f"\nPipeline aborted at stage {i}/{total}: {stem}", file=sys.stderr)
            sys.exit(1)

    print(f"\n{'='*62}")
    print("  Pipeline complete!")
    print(f"{'='*62}\n")


if __name__ == "__main__":
    main()
