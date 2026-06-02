"""SDK quickstart — collective resolution, a reversible split, and undo.

Run: uv run python examples/quickstart.py   (zero deps: sqlite + in-memory graph)
"""

from __future__ import annotations

from reconcile import Reconciler

rec = Reconciler.local(database_url="sqlite:///./_quickstart.db")

# --- Scenario A: collective resolution + reversible split -----------------
# Two look-alike companies that are actually distinct (different domains + IDs)
# plus two true duplicates of a third company.
rec.ingest(
    mentions=[
        {"id": "acme-inc",  "name": "Acme Inc",  "type": "Company",
         "attributes": {"domain": "acme.com",     "external_id": "SF-001"}},
        {"id": "acme-corp", "name": "Acme Corp", "type": "Company",
         "attributes": {"domain": "acme-corp.io", "external_id": "SF-002"}},
        # true duplicates (same domain) — used for the undo scenario below
        {"id": "globex-1", "name": "Globex", "type": "Company", "attributes": {"domain": "g.com"}},
        {"id": "globex-2", "name": "Globex", "type": "Company", "attributes": {"domain": "g.com"}},
    ],
)
rec.resolve()
print("A. collective keeps look-alikes separate:", not rec.same_cluster("acme-inc", "acme-corp"))

rec.submit_decision("acme-inc", "acme-corp", same=True)            # a naive forced merge
print("   after a forced merge, they share a node:", rec.same_cluster("acme-inc", "acme-corp"))

rec.split("acme-inc", "acme-corp", evidence={"reason": "distinct Salesforce accounts"})
print("   reversible split separates them again:", not rec.same_cluster("acme-inc", "acme-corp"))

# --- Scenario B: undo (retract) on a genuine duplicate --------------------
print("\nB. the two 'Globex' mentions auto-merge:", rec.same_cluster("globex-1", "globex-2"))
rec.split("globex-1", "globex-2", evidence={"reason": "mistaken split"})
print("   a (wrong) human split separates them:", not rec.same_cluster("globex-1", "globex-2"))
rec.retract("globex-1", "globex-2")                                # undo the split
print("   retract undoes it; they re-merge:", rec.same_cluster("globex-1", "globex-2"))

print("\nchange events:")
for e in rec.events():
    print(f"  {e.kind.value}: {e.old_ids} -> {e.new_ids}")

rec.close()
