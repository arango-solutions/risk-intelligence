"""
generate_clean_portfolio.py

Generates a realistic population of CLEAN (non-sanctioned) counterparties so the
risk heatmap shows risk as the *exception* rather than the rule. Without this,
the loaded data is essentially the entire OFAC SDN list, so ~99.9% of nodes are
sanctioned (high risk) and the heatmap is uniformly red.

What it creates (all idempotent — CLEAN-* docs/edges are wiped and rebuilt):
  - Clean Organizations and Persons (dataSource="CleanPortfolio", riskScore=0)
  - A believable internal network among them (ownership trees, leadership, family)
    that carries NO risk (everyone stays green)
  - A small number of "exposure" links from a few clean entities into real
    sanctioned OFAC anchors, at varying hop distances, so those few light up
    high/medium/low after inferred-risk propagation — the demo hotspots.

Pipeline position: run AFTER calculate_direct_risk (so anchors have riskScore)
and BEFORE calculate_inferred_risk (so exposure propagates).

Run:
    python scripts/generate_clean_portfolio.py
    python scripts/calculate_inferred_risk.py   # propagate
"""

from __future__ import annotations

import os
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import apply_config_to_env, get_arango_config, load_dotenv, sanitize_url

from arango import ArangoClient

SEED = 20260528
NUM_ORGS = 120
NUM_PERSONS = 180
CLEAN_SOURCE = "CleanPortfolio"

ORG_ADJ = ["Atlantic", "Summit", "Pioneer", "Cascade", "Meridian", "Granite", "Harbor",
           "Cedar", "Vanguard", "Northwind", "Brightwater", "Ironwood", "Silverline",
           "Evergreen", "Keystone", "Riverstone", "Lakeside", "Highland", "Coral", "Aspen"]
ORG_NOUN = ["Logistics", "Holdings", "Trading", "Capital", "Industries", "Shipping",
            "Maritime", "Partners", "Ventures", "Freight", "Resources", "Systems",
            "Imports", "Exports", "Commodities", "Group", "Enterprises", "Manufacturing"]
ORG_SUFFIX = ["LLC", "Inc.", "Ltd.", "Corp.", "GmbH", "S.A.", "Pte. Ltd.", "B.V."]

FIRST = ["James", "Maria", "David", "Sarah", "Michael", "Linda", "Robert", "Emma",
         "John", "Olivia", "William", "Sophia", "Daniel", "Grace", "Thomas", "Chloe",
         "Henry", "Ava", "George", "Lucy", "Edward", "Mia", "Charles", "Nora",
         "Arthur", "Ruth", "Samuel", "Iris", "Peter", "Hazel"]
LAST = ["Hartwell", "Bennett", "Caldwell", "Donovan", "Ellis", "Forsythe", "Greaves",
        "Holloway", "Ingram", "Jennings", "Kingsley", "Lockhart", "Mercer", "Nolan",
        "Osborne", "Prescott", "Quinn", "Radcliffe", "Sinclair", "Thornton", "Underwood",
        "Vance", "Whitfield", "Yates", "Ashby", "Barlow", "Conway", "Dalton"]


def main():
    load_dotenv()
    cfg = get_arango_config()
    apply_config_to_env(cfg)
    print(f"Connecting to ArangoDB ({cfg.mode}): {sanitize_url(cfg.url)}")
    print(f"Database: {cfg.database}\n")

    client = ArangoClient(hosts=cfg.url)
    db = client.db(cfg.database, username=cfg.username, password=cfg.password)
    rng = random.Random(SEED)

    # ------------------------------------------------------------------
    # 0. Wipe any previous clean-portfolio docs/edges (idempotent rebuild)
    # ------------------------------------------------------------------
    print("Removing any existing CleanPortfolio docs/edges...")
    for coll in ["Person", "Organization", "owned_by", "leader_of", "family_member_of"]:
        if db.has_collection(coll):
            db.aql.execute(
                f"FOR d IN {coll} FILTER d.dataSource == @s REMOVE d IN {coll}",
                bind_vars={"s": CLEAN_SOURCE},
            )

    # ------------------------------------------------------------------
    # 1. Find real sanctioned anchors (high direct risk) to attach exposure to
    # ------------------------------------------------------------------
    def anchors(coll, n):
        # Prefer LOW-degree sanctioned entities (few/no subsidiaries or other
        # links). A high-degree anchor like a big sanctioned conglomerate would
        # drag its whole red subsidiary network onto the canvas when expanded,
        # flooding the otherwise-green portfolio view.
        return list(db.aql.execute(
            f"""FOR d IN {coll}
                FILTER (d.riskScore || 0) >= 0.9 AND d.dataSource != @s
                LET deg = LENGTH(FOR e IN owned_by
                                 FILTER e._to == d._id OR e._from == d._id RETURN 1)
                        + LENGTH(FOR e IN leader_of
                                 FILTER e._to == d._id OR e._from == d._id RETURN 1)
                        + LENGTH(FOR e IN family_member_of
                                 FILTER e._to == d._id OR e._from == d._id RETURN 1)
                SORT deg ASC, RAND()
                LIMIT @n RETURN d._id""",
            bind_vars={"s": CLEAN_SOURCE, "n": n},
        ))

    org_anchors = anchors("Organization", 4)
    person_anchors = anchors("Person", 2)
    if not org_anchors:
        print("[WARN] No sanctioned Organization anchors found — run calculate_direct_risk first.")
    print(f"Anchors: {len(org_anchors)} orgs, {len(person_anchors)} persons")

    # ------------------------------------------------------------------
    # 2. Generate clean entities
    # ------------------------------------------------------------------
    orgs, persons = [], []
    used_names = set()

    def org_name():
        while True:
            nm = f"{rng.choice(ORG_ADJ)} {rng.choice(ORG_NOUN)} {rng.choice(ORG_SUFFIX)}"
            if nm not in used_names:
                used_names.add(nm)
                return nm

    def person_name():
        while True:
            nm = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
            if nm not in used_names:
                used_names.add(nm)
                return nm

    for i in range(1, NUM_ORGS + 1):
        key = f"CLEAN-ORG-{i:04d}"
        nm = org_name()
        orgs.append({"_key": key, "primaryName": nm, "label": nm, "party_id": key,
                     "dataSource": CLEAN_SOURCE, "scenario": "portfolio", "riskScore": 0,
                     "inferredRisk": 0})
    for i in range(1, NUM_PERSONS + 1):
        key = f"CLEAN-PER-{i:04d}"
        nm = person_name()
        persons.append({"_key": key, "primaryName": nm, "label": nm, "party_id": key,
                        "dataSource": CLEAN_SOURCE, "scenario": "portfolio", "riskScore": 0,
                        "inferredRisk": 0})

    db.collection("Organization").import_bulk(orgs, overwrite=False, on_duplicate="replace")
    db.collection("Person").import_bulk(persons, overwrite=False, on_duplicate="replace")
    print(f"Inserted {len(orgs)} clean Organizations, {len(persons)} clean Persons")

    org_ids = [f"Organization/{o['_key']}" for o in orgs]
    per_ids = [f"Person/{p['_key']}" for p in persons]

    # ------------------------------------------------------------------
    # Reserve a small, isolated "exposure zone" up front. These few entities
    # (and only these) connect to sanctioned anchors. They are deliberately
    # excluded from the internal clean network so risk cannot cascade from a
    # hotspot into the rest of the portfolio (owned_by risk flows owner->
    # subsidiary, so an exposed *owner* would otherwise contaminate everything
    # it owns). The clean zone is the large remainder and stays green.
    # ------------------------------------------------------------------
    N_EXPO_ORG = 6   # org indices 0..5 are exposure-only
    N_EXPO_PER = 2   # person indices 0..1 are exposure-only
    clean_org_ids = org_ids[N_EXPO_ORG:]
    clean_per_ids = per_ids[N_EXPO_PER:]

    owned, leads, family = [], [], []
    eid = 0

    def ek():
        nonlocal eid
        eid += 1
        return f"CLEAN-E-{eid:05d}"

    # ------------------------------------------------------------------
    # 3. Internal clean network (clean zone only — carries NO risk)
    # ------------------------------------------------------------------
    # Ownership forest among clean-zone orgs: a few roots, everyone else owned
    # by an earlier clean-zone org (parents are always clean, so no risk flows).
    roots = set(rng.sample(range(len(clean_org_ids)), k=max(6, len(clean_org_ids) // 12)))
    for idx in range(1, len(clean_org_ids)):
        if idx in roots:
            continue
        owned.append({"_key": ek(), "_from": clean_org_ids[idx],
                      "_to": clean_org_ids[rng.randrange(idx)],
                      "label": "owned_by", "dataSource": CLEAN_SOURCE})

    # Leadership: most clean persons lead some clean-zone org.
    for pid in clean_per_ids:
        if rng.random() < 0.85:
            leads.append({"_key": ek(), "_from": pid, "_to": rng.choice(clean_org_ids),
                          "label": "leader_of", "dataSource": CLEAN_SOURCE})

    # Family ties among a subset of clean-zone persons.
    for _ in range(len(clean_per_ids) // 4):
        a, b = rng.sample(clean_per_ids, 2)
        family.append({"_key": ek(), "_from": a, "_to": b, "label": "family_member_of",
                       "dataSource": CLEAN_SOURCE})

    # ------------------------------------------------------------------
    # 4. Exposure links into sanctioned anchors (the contained hotspots)
    #    owned_by decay = 0.85/hop: 1 hop=0.85(hi) 2=0.72(hi) 3=0.61(med)
    #    4=0.52(med) 5=0.44(med); family=0.5(med); family-of-family=0.25(low).
    #    Exposure-zone orgs own nothing else, so risk stops at the chain.
    # ------------------------------------------------------------------
    exposures = 0
    if org_anchors:
        # (a) Direct high: org[0] owned_by a sanctioned org (leaf -> stops here).
        owned.append({"_key": ek(), "_from": org_ids[0], "_to": org_anchors[0],
                      "label": "owned_by", "dataSource": CLEAN_SOURCE}); exposures += 1

        # (b) A 5-deep ownership chain off a sanctioned anchor: org1..org5 graded
        #     hi -> hi -> med -> med -> med. org5 is a leaf so it stops there.
        chain = org_ids[1:6]
        owned.append({"_key": ek(), "_from": chain[0],
                      "_to": org_anchors[min(1, len(org_anchors) - 1)],
                      "label": "owned_by", "dataSource": CLEAN_SOURCE}); exposures += 1
        for parent, child in zip(chain, chain[1:]):
            owned.append({"_key": ek(), "_from": child, "_to": parent,
                          "label": "owned_by", "dataSource": CLEAN_SOURCE}); exposures += 1

    if person_anchors:
        # (c) Family exposure: clean person related to a sanctioned person -> medium.
        family.append({"_key": ek(), "_from": per_ids[0], "_to": person_anchors[0],
                       "label": "family_member_of", "dataSource": CLEAN_SOURCE}); exposures += 1
        # (d) Family-of-family: another clean person -> low.
        family.append({"_key": ek(), "_from": per_ids[1], "_to": per_ids[0],
                       "label": "family_member_of", "dataSource": CLEAN_SOURCE}); exposures += 1

    db.collection("owned_by").import_bulk(owned, overwrite=False, on_duplicate="replace")
    db.collection("leader_of").import_bulk(leads, overwrite=False, on_duplicate="replace")
    db.collection("family_member_of").import_bulk(family, overwrite=False, on_duplicate="replace")
    print(f"Inserted {len(owned)} owned_by, {len(leads)} leader_of, {len(family)} family edges "
          f"({exposures} of them are sanctioned-exposure links)")

    print("\nDone. Now run: python scripts/calculate_inferred_risk.py")


if __name__ == "__main__":
    main()
