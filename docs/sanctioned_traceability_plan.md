# Traceability to Highly Sanctioned Entities

**Status:** Implemented (v1) — June 3, 2026
**Decision:** Built additively inside `risk-intelligence` (not a fork). See "Fork triggers" for the exceptions.

## Implemented in v1
- **Source tagging** — `calculate_direct_risk.py` now writes `sanctionsSources` (e.g. `["OFAC SDN"]`) on every flagged entity, so a trace reports *which* list flagged the target. This is also the seam for future jurisdictions (EU/UN/OFSI) — no downstream changes needed.
- **"Trace to sanctioned source" canvas action** — right-click a node in the Visualizer (DataGraph / KnowledgeGraph) to return the shortest path(s) to the nearest highly sanctioned entity (`riskScore >= 0.9`), rendered as an explainable hop-by-hop subgraph.

## Deferred (open questions / later workstreams)
- Optional precompute of `nearestSanctionedHops` (§3.4) — not built; ship-first decision.
- Direction-aware variant (§3.3) — defaulted to `ANY`.
- Multi-jurisdiction ingestion — separate workstream (must normalize + entity-resolve; see "Fork triggers").

---

## 1. Goal

Given any focal entity, return the **explainable relationship path(s)** connecting it to the nearest **highly sanctioned** entity, within a bounded number of hops — and surface this in the Visualizer (right-click action + Queries panel).

This is the explainability layer on top of the existing `inferredRisk` propagation: propagation says *how risky* a node is; traceability shows *the path that makes it risky*. It lets us trace to entities **actually on a sanctions list**, not merely to countries or jurisdictions of concern.

---

## 2. What we already have (reuse, don't rebuild)

| Asset | Reuse for traceability |
|---|---|
| Collections `Person`, `Organization`, `Vessel`, `Aircraft` | Vertices to traverse |
| Edges `owned_by`, `leader_of`, `family_member_of`, `operates` | Relationship paths (ownership, leadership, family, operating links) |
| `riskScore` (from OFAC SDN ListID; SDN `1550` → `1.0`) | Indexable "highly sanctioned" predicate (`riskScore >= 0.9`) |
| `inferredRisk` / `riskLevel` | Complementary risk magnitude; not changed by this work |
| `install_theme.py` canvas-action + saved-query installers | Drop-in integration point |

No new data sources, collections, or risk-math changes required.

---

## 3. Approach

### 3.1 "Highly sanctioned" definition
- Default predicate: `riskScore >= 0.9` (configurable). Captures OFAC SDN list (`1.0`).
- Optional stricter mode: only entities directly on the SDN list (vs. inferred).

### 3.2 Core query (bounded traversal, prune at sanctioned nodes)
Find the nearest sanctioned endpoint(s) from a focal node and return the path:

```aql
WITH Person, Organization, Vessel, Aircraft
FOR v, e, p IN 1..@maxHops ANY @start
     owned_by, leader_of, family_member_of, operates
  PRUNE (v.riskScore || 0) >= @threshold
  OPTIONS { uniqueVertices: "path", bfs: true }
  FILTER (v.riskScore || 0) >= @threshold
  RETURN { hops: LENGTH(p.edges), path: p.vertices[*]._id, edges: p.edges[*]._id,
           target: v._id, targetRisk: v.riskScore }
```

- `PRUNE` stops expanding once a sanctioned node is reached → returns the *nearest* exposure, not deeper noise.
- `bfs: true` + `uniqueVertices: "path"` → shortest-first, no cycles.
- Returns full vertex+edge path for hop-by-hop justification.

### 3.3 Direction semantics (design decision needed)
- A direction-blind `ANY` traversal is the simplest and matches the demo's current expand behavior.
- For the more precise question "is this counterparty exposed to a sanctioned **owner/controller**?", `INBOUND`/`OUTBOUND` on `owned_by`/`leader_of` is better.
- **Proposal:** default to `ANY` for simplicity; expose a directional variant as a second action if needed.

### 3.4 Optional precompute (pipeline stage)
- Add `nearestSanctionedHops` (+ optional stored path) per node during the pipeline (extend `calculate_inferred_risk.py` or a new stage).
- Benefit: instant lookup, sortable/filterable risk signal, and a theme rule could color by "distance to sanctioned source."
- Cost: extra pipeline pass; recompute on data change.

---

## 4. Deliverables

1. **Trace query** (saved query in `_queries` → "Trace to Sanctioned Source"), parameterized by `@start`, `@maxHops`, `@threshold`.
2. **Canvas action** "Trace to sanctioned source" (right-click a node), using `@nodes`, `RETURN p` (mirrors existing Expand actions in `install_theme.py`).
3. *(Optional, if chosen)* Pipeline precompute of `nearestSanctionedHops` + a heatmap-style theme rule.
4. Short README/demo-walkthrough note on how to run it.

---

## 5. Effort & risk

- **Effort:** ~0.5–1 day for items 1–2 (query + canvas action + saved query, following existing patterns). +0.5–1 day if precompute (item 3) is included.
- **Risk:** Low. Purely additive — no changes to existing collections, edges, or risk calculation. Main watch-item is **super-node / path explosion** on dense sanctioned hubs (a common failure mode); mitigated by `PRUNE`, `bfs`, `uniqueVertices: "path"`, `@maxHops` (default 3–4), and a `LIMIT`.

---

## 6. Open questions

1. Threshold for "highly sanctioned": `riskScore >= 0.9`, or SDN-list-only?
2. Default max hops (3? 4?) and whether to cap results per focal node.
3. Direction-aware variant needed for the demo, or is `ANY` sufficient?
4. Include the optional precompute now, or ship query/action first and add later?
5. Apply to both `DataGraph` and `KnowledgeGraph`, or DataGraph only?

---

## 7. Fork triggers (when this should NOT live here)

- We decide to **ingest a third-party aggregated sanctions feed** (e.g., a denormalized external dataset) and demonstrate a normalization + entity-resolution migration (divergent ingestion + schema).
- It becomes a **engagement-specific / branded deliverable** that will diverge from the clean reference demo.

Neither applies to the capability itself, so the recommendation stands: build additively here.
