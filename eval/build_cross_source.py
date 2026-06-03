"""Build the cross-source graph: structured CRM contacts + messy prose mentions.

Two genuinely overlapping real sources from People.ai:
  - structured: accounts + contacts (with email anchors) from `crm.json`
  - prose: company/person mentions extracted from real account-activity summaries
    (`prose.json`) — NO anchors, names as they appear in the text

The prose company "HyperScience" shares no string with "ABBYY"; it can only be linked
to the ABBYY account *through shared people* — and only after those prose people resolve
to the structured contacts. That two-hop is what exercises collective propagation.

Outputs `eval/real/cross_graph.json` and `eval/real/cross_labels.json`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REAL = Path(__file__).parent / "real"


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _pkey(s: str) -> str:
    """Order-invariant person key so 'Mikael Ward' matches structured 'Ward Mikael'."""
    return " ".join(sorted(_norm(s).split()))


def build():
    crm = json.loads((REAL / "crm.json").read_text())
    prose = json.loads((REAL / "prose.json").read_text())

    mentions: dict[str, dict] = {}
    relationships: list[dict] = []

    def add(mid, name, etype, attrs):
        mentions.setdefault(mid, {"id": mid, "name": name, "type": etype, "attributes": attrs})

    # ---- structured side (canonical, anchored) ----------------------------
    # name(normalized) -> structured person id, per account, to wire prose->structured gold
    struct_person_by_account: dict[int, dict[str, str]] = {}
    for acct in crm["accounts"]:
        aid = acct["peopleai_account_id"]
        am = f"acct-{aid}"
        add(am, acct["name"], "Company", {"external_id": str(aid), "domain": acct["domain"]})
        struct_person_by_account[aid] = {}
        for c in acct["external_contacts"] + acct.get("internal_team", []):
            email = c["email"].lower()
            pid = f"person-{email}"
            add(pid, c["name"], "Person", {"email": email, "domain": email.split("@")[1]})
            relationships.append({"src": am, "dst": pid, "type": "ENGAGED_WITH"})
            struct_person_by_account[aid][_pkey(c["name"])] = pid

    account_ids = [a["peopleai_account_id"] for a in crm["accounts"]]

    # ---- prose side (messy, no anchors) -----------------------------------
    labels: list[dict] = []
    for pa in prose["prose_accounts"]:
        aid = pa["account_id"]
        # prose person mentions
        prose_people = []
        for person in pa["people"]:
            pid = f"prose-person-{aid}-{_slug(person)}"
            add(pid, person, "Person", {})  # no email anchor
            prose_people.append(pid)
            # gold: this prose person is the structured contact of the same name in the account
            struct = struct_person_by_account.get(aid, {}).get(_pkey(person))
            if struct:
                labels.append({"a": pid, "b": struct, "label": "same", "category": "person_link"})
        # prose company surface forms, each connected to the prose people
        for form in pa["company_surface_forms"]:
            cid = f"prose-co-{aid}-{_slug(form)}"
            add(cid, form, "Company", {})  # no anchor
            for pid in prose_people:
                relationships.append({"src": cid, "dst": pid, "type": "MENTIONED_WITH"})
            # gold: company form -> its account (same); -> other accounts (different)
            for other in account_ids:
                labels.append({"a": cid, "b": f"acct-{other}",
                               "label": "same" if other == aid else "different",
                               "category": "company_link" if other == aid else "company_wrong"})

    (REAL / "cross_graph.json").write_text(json.dumps(
        {"mentions": list(mentions.values()), "relationships": relationships}, indent=2))
    (REAL / "cross_labels.json").write_text(json.dumps(labels, indent=2))

    n_prose_co = sum(1 for m in mentions.values() if m["id"].startswith("prose-co-"))
    n_prose_p = sum(1 for m in mentions.values() if m["id"].startswith("prose-person-"))
    cats: dict[str, int] = {}
    for label in labels:
        cats[label["category"]] = cats.get(label["category"], 0) + 1
    print(f"structured: {len(account_ids)} accounts; "
          f"prose: {n_prose_co} company-forms, {n_prose_p} person-mentions")
    print(f"labels: {len(labels)} {cats}")
    return mentions, relationships, labels


if __name__ == "__main__":
    build()
