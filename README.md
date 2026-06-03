# Sentries: Risk Intelligence Knowledge Graph

Sentries is an advanced graph intelligence platform for demonstrating ArangoDB AI.
It leverages the OFAC Specially Designated Nationals (SDN) dataset to identify and
propagate transitive risk through complex ownership, leadership, and familial networks.

## Features

- **RDF-to-Property Graph** – Automatic schema mapping from an OWL ontology to ArangoDB collections.
- **Dynamic Risk Vetting** – AQL path-based engine that calculates real-time threat exposure via transitive relationships.
- **Visual Intelligence** – Custom ArangoDB Visualizer themes for structural exploration and risk heatmaps.
- **Expert Analytics** – Built-in library of saved queries for threat discovery and portfolio risk concentration.

---

## Quick Start

### 1. Prerequisites

- Python 3.8+
- ArangoDB 3.10+ with the Graph Visualizer extension enabled
- An OFAC SDN Advanced XML download (see [Getting OFAC Data](#getting-ofac-data) below)

### 2. Clone & Install

```bash
git clone https://github.com/ArthurKeen/risk-intelligence.git
cd risk-intelligence
pip install -r requirements.txt
```

### 3. Configure

```bash
cp template.env .env
# Edit .env with your ArangoDB endpoint, username, and password
```

### 4. Getting OFAC Data

The pipeline requires the **OFAC SDN Advanced XML** file:

1. Visit the US Treasury sanctions page:
   <https://sanctionslist.ofac.treas.gov/Home/SdnList>
2. Download **SDN_ADVANCED.XML** (the "Advanced XML format" link).
3. Place it at `data/SDN_ADVANCED.XML` in this repository root.

> The file is ~50 MB and changes frequently. It is excluded from version control
> (`.gitignore`). Re-download it whenever you need fresh OFAC data.

Then flatten it to CSVs:

```bash
python scripts/flatten_ofac.py   # produces data/parties.csv and data/relationships.csv
```

### 5. Run the Full Pipeline

```bash
python scripts/run_pipeline.py
```

This single command runs all stages in order:

| Stage | Script | What it does |
|-------|--------|--------------|
| 1 | `load_data.py` | Loads ontology + OFAC CSV data + synthetic fixtures |
| 2 | `calculate_direct_risk.py` | Assigns `riskScore` from OFAC SDN list |
| 3 | `generate_clean_portfolio.py` | Adds clean (non-sanctioned) counterparties + a few sanctioned-exposure hotspots |
| 4 | `calculate_inferred_risk.py` | Propagates `inferredRisk` (0.85/hop ownership decay) + writes `riskLevel` |
| 5 | `install_theme.py` | Installs Visualizer themes, canvas actions & saved queries |

> **Why the clean portfolio?** The loaded OFAC data is essentially the entire SDN
> list, so ~99.9% of nodes are sanctioned (high risk) — without clean
> counterparties the heatmap is uniformly red. `generate_clean_portfolio.py`
> injects ~120 clean Organizations and ~180 clean Persons that stay green, with a
> small, *isolated* set of entities wired into sanctioned anchors so risk
> propagates outward into a high → medium → low gradient (the demo hotspots).

Selective flags:

```bash
python scripts/run_pipeline.py --skip-data      # skip load_data (data already in DB)
python scripts/run_pipeline.py --only-themes    # only run install_theme.py
```

### 6. Load Demo Test Data

After the pipeline, generate the specific demo scenarios for the walkthrough:

```bash
python scripts/generate_test_data.py
```

This loads **Scenarios D & E** (Shell Game + Proxy Link) and verifies expected risk
values. See [docs/demo_walkthrough.md](docs/demo_walkthrough.md) for the full guide.

---

## Demo Walkthrough

Open the ArangoDB UI → **Graphs** → **KnowledgeGraph**.
Select the **sentries_risk_heatmap** theme from the Legend drop-down (it is not the
default theme — the built-in **Default** theme is, so the heatmap stays editable).

The heatmap colors nodes directly from the `inferredRisk` score using ordered,
first-match-wins attribute rules:

| Color | Hex | Meaning |
|-------|-----|---------|
| Red | `#e53e3e` | `inferredRisk ≥ 0.7` (high) |
| Yellow | `#d69e2e` | `0.3 < inferredRisk < 0.7` (medium) |
| Green | `#48bb78` | `inferredRisk ≤ 0.3` (low) |

The `sentries_standard` theme uses a separate cool/neutral palette (blue, purple,
teal, slate) so entity-type coloring is never confused with the red/yellow/green
risk colors.

Use the **Queries** panel (Visualizer sidebar) → **"Load Demo Scenarios"** to bring
all synthetic entities onto the canvas at once, or **"Risk Portfolio (mostly clean)"**
to load the clean counterparty portfolio — a mostly-green graph with a handful of
high/medium/low hotspots where exposure to sanctioned anchors propagates inward.

**Trace to a sanctioned source:** right-click any node → **"Trace to sanctioned
source"** to render the shortest path(s) from that entity to the nearest highly
sanctioned party (`riskScore >= 0.9`). Each sanctioned entity is tagged with a
`sanctionsSources` attribute (e.g. `OFAC SDN`) recording which list flagged it.
See [docs/sanctioned_traceability_plan.md](docs/sanctioned_traceability_plan.md).

See [docs/demo_walkthrough.md](docs/demo_walkthrough.md) for step-by-step instructions.

---

## Troubleshooting

### Theme shows no colors (all grey nodes)

The most common cause is that `calculate_inferred_risk.py` has not been run, so nodes
lack the `riskLevel` attribute. Re-run the pipeline or just:

```bash
python scripts/calculate_inferred_risk.py
python scripts/install_theme.py
```

### "Nothing returned" in the Visualizer search bar

The built-in search in older Visualizer versions requires an ArangoSearch view on
the collection. Use the **Queries** panel saved query instead, or run the AQL directly
in the Query Editor:

```aql
FOR d IN Organization FILTER d.dataSource == 'Synthetic' RETURN d
```

### `load_data.py` fails with ERR 1921

This happens if the DB already has edge definitions from a previous run.
The script handles this via `_upsert_edge_def`; if it still occurs, drop the
`KnowledgeGraph` graph object (not the collections) and re-run.

### Authentication errors with MCP servers

Each project uses its own MCP server. The Cursor rule `.cursor/rules/arango-mcp.mdc`
pins this project to `user-arangodb-risk-intelligence-mcp`. If you see auth errors,
verify that `~/.cursor/mcp.json` has the correct credentials for the
`arangodb-risk-intelligence-mcp` entry.

---

## Architecture

```
OWL Ontology ──► OntologyGraph (schema)
OFAC XML     ──► parties.csv + relationships.csv ──► KnowledgeGraph (data)
Synthetic CSV ──► KnowledgeGraph (demo fixtures)
                      │
                      ▼
          calculate_direct_risk.py   (riskScore)
          calculate_inferred_risk.py (inferredRisk + riskLevel)
                      │
                      ▼
          install_theme.py  ──► _graphThemeStore, _canvasActions, _queries
```

## License

MIT
