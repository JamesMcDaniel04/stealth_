"""Build the real-data validation graph from the People.ai CRM snapshot.

Canonical side (100% real): one Company mention per account (anchored by the
People.ai account id + domain) and one Person mention per distinct contact email,
joined by ENGAGED_WITH edges. Contacts are deduped by email, so a partner who
appears on two accounts (aiden.clark@deloitte.com) is ONE shared neighbor, while two
different people who happen to share a name (anna.king@nuance.com vs
anna.king@samsclub.com) are two distinct mentions.

Injected side (controlled): for each account, a messy "call mention" of the company
under a variant name (WD, KKR, ...) with NO anchor, attached to a few of that
account's REAL contacts. Only the surface name is synthetic; the relationship signal
is real. Gold labels are known by construction.

Outputs `eval/real/graph.json` (mentions + relationships) and `eval/real/labels.json`
(pairs with gold same/different + category).
"""

from __future__ import annotations

import json
import re
from itertools import combinations
from pathlib import Path

REAL = Path(__file__).parent / "real"
CRM = REAL / "crm.json"
GRAPH_OUT = REAL / "graph.json"
LABELS_OUT = REAL / "labels.json"

# how many of an account's real external contacts a call-mention "mentions"
VARIANT_CONTACTS = 3


def _norm_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def _email_domain(email: str) -> str:
    return email.split("@", 1)[1] if "@" in email else ""


def build():
    data = json.loads(CRM.read_text())
    accounts = data["accounts"]
    variants = {v["account_id"]: v for v in data.get("injected_company_variants", [])}

    mentions: dict[str, dict] = {}
    relationships: list[dict] = []

    def add_mention(mid, name, etype, attrs):
        if mid not in mentions:
            mentions[mid] = {"id": mid, "name": name, "type": etype, "attributes": attrs}

    # account id -> its external contact mention ids (for variant attachment + labels)
    acct_external: dict[int, list[str]] = {}

    for acct in accounts:
        aid = acct["peopleai_account_id"]
        acct_mid = f"acct-{aid}"
        add_mention(acct_mid, acct["name"], "Company",
                    {"external_id": str(aid), "domain": acct["domain"]})

        externals = []
        for group, contacts in (("ext", acct["external_contacts"]),
                                 ("int", acct.get("internal_team", []))):
            for c in contacts:
                email = c["email"].lower()
                pid = f"person-{email}"
                add_mention(pid, c["name"], "Person",
                            {"email": email, "domain": _email_domain(email)})
                relationships.append({"src": acct_mid, "dst": pid, "type": "ENGAGED_WITH"})
                if group == "ext":
                    externals.append(pid)
        acct_external[aid] = externals

    # injected company-name variants (call mentions), attached to real contacts
    variant_to_account: dict[str, int] = {}
    for aid, v in variants.items():
        vid = f"callmention-{aid}"
        add_mention(vid, v["variant_name"], "Company", {})  # no anchor
        for pid in acct_external.get(aid, [])[:VARIANT_CONTACTS]:
            relationships.append({"src": vid, "dst": pid, "type": "MENTIONED_WITH"})
        variant_to_account[vid] = aid

    # ---- ground-truth labels (auto, by construction) ----------------------
    labels: list[dict] = []

    def add_label(a, b, same, category):
        labels.append({"a": a, "b": b, "label": "same" if same else "different",
                       "category": category})

    account_ids = [a["peopleai_account_id"] for a in accounts]

    # 1. company variant -> its account (same) and -> other accounts (different)
    for vid, aid in variant_to_account.items():
        for other in account_ids:
            add_label(vid, f"acct-{other}", same=(other == aid),
                      category="variant_link" if other == aid else "variant_wrong")

    # 2. account <-> account (distinct companies)
    for a, b in combinations(account_ids, 2):
        add_label(f"acct-{a}", f"acct-{b}", same=False, category="account_pair")

    # 3. person name-collisions: same normalized name, different email -> different
    by_name: dict[str, set[str]] = {}
    for m in mentions.values():
        if m["type"] == "Person":
            by_name.setdefault(_norm_name(m["name"]), set()).add(m["id"])
    for ids in by_name.values():
        for a, b in combinations(sorted(ids), 2):
            add_label(a, b, same=False, category="person_collision")

    GRAPH_OUT.write_text(json.dumps(
        {"mentions": list(mentions.values()), "relationships": relationships},
        indent=2))
    LABELS_OUT.write_text(json.dumps(labels, indent=2))

    n_people = sum(1 for m in mentions.values() if m["type"] == "Person")
    n_company = sum(1 for m in mentions.values() if m["type"] == "Company")
    cats: dict[str, int] = {}
    for label in labels:
        cats[label["category"]] = cats.get(label["category"], 0) + 1
    print(f"graph: {n_company} companies ({len(variant_to_account)} variants), "
          f"{n_people} people, {len(relationships)} edges")
    print(f"labels: {len(labels)} pairs {cats}")
    return mentions, relationships, labels


if __name__ == "__main__":
    build()
