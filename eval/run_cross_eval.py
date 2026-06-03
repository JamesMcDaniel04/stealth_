"""Cross-source linking: can resolution link a messy prose company mention to the right
structured CRM account — and does it take collective *propagation* to do it?

For each prose company form we compare three things on linking it to its account:
  - embedding-only: similarity of the names alone
  - pairwise (round 0): relational score before any propagation (prose people not yet merged
    with structured contacts, so no shared neighbors exist yet)
  - collective (full): same-cluster after propagation (prose people merge with structured
    contacts first, which then gives the company a shared neighborhood — two-hop)

The "HyperScience" -> ABBYY case (zero name overlap) is the one that needs propagation.
"""

from __future__ import annotations

import json
from pathlib import Path

from reconcile.dataset import _mentions_from, _relationships_from
from reconcile.embeddings import make_embedder
from reconcile.resolution.collective import CollectiveResolver
from reconcile.resolution.features import FeatureContext
from reconcile.resolution.scorer import WeightedRuleScorer, embedding_only_prob

REAL = Path(__file__).parent / "real"


def run():
    graph = json.loads((REAL / "cross_graph.json").read_text())
    labels = json.loads((REAL / "cross_labels.json").read_text())
    mentions = _mentions_from(graph["mentions"])
    relationships = _relationships_from(graph["relationships"])
    name = {m.id: m.name for m in mentions}

    embedder = make_embedder()
    ctx = FeatureContext.build(mentions, relationships, embedder=embedder)
    scorer = WeightedRuleScorer()
    result = CollectiveResolver(ctx, scorer).resolve()
    rep = result.rep_map
    print(f"embedder: {embedder.model_id}")

    gold = {p["a"]: p["b"] for p in labels if p["category"] == "company_link"}

    # did the bootstrap happen? prose people merging with structured contacts
    person_links = [p for p in labels if p["category"] == "person_link"]
    merged_people = sum(1 for p in person_links if rep.get(p["a"]) == rep.get(p["b"]))
    print(f"\nbootstrap: {merged_people}/{len(person_links)} prose people merged with their "
          f"structured contact (this is what enables the two-hop)")

    print("\n=== Link each prose company mention to a CRM account ===")
    print(f"{'prose company':<14} {'gold account':<28} {'name':>5} {'emb_p':>6} "
          f"{'pairwise_p':>11} {'collective':>22}")
    em_ok = pw_ok = col_ok = 0
    for cid, acct in gold.items():
        f0 = ctx.features(cid, acct)
        emb = embedding_only_prob(f0.embedding_cosine)
        pw = scorer.score(f0)[0]  # round-0 relational (no propagation)
        # collective: which account (if any) shares its cluster
        linked = [m.id for m in mentions
                  if m.id.startswith("acct-") and rep.get(m.id) == rep.get(cid)]
        col_acct = linked[0] if linked else None
        col_correct = col_acct == acct
        em_ok += emb >= 0.5
        pw_ok += pw >= 0.5
        col_ok += col_correct
        col_str = (f"-> {name[col_acct]}" if col_acct else "(unlinked)")
        print(f"{name[cid]:<14} {name[acct]:<28} {f0.name_sim:>5.2f} {emb:>6.2f} "
              f"{pw:>11.2f} {('OK ' if col_correct else 'X  ') + col_str:>22}")

    n = len(gold)
    print(f"\nlinked to correct account:  embedding-only(@0.5)={em_ok}/{n}   "
          f"pairwise(@0.5)={pw_ok}/{n}   collective(clustered)={col_ok}/{n}")
    print("\nThe HyperScience -> ABBYY link (name 0.00) is invisible to embeddings and to")
    print("pairwise scoring; it appears only after collective propagation merges the shared")
    print("people — the first real-data case that needs propagation, not just relational features.")
    return {"embedding": em_ok, "pairwise": pw_ok, "collective": col_ok, "n": n}


if __name__ == "__main__":
    run()
