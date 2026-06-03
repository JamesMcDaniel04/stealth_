"""Spot-check the auto-derived gold labels: print the hardest pairs with evidence so a
human can confirm the numbers are trustworthy. (Labels are auto-derived by construction;
this surfaces them for review, not to re-label.)
"""

from __future__ import annotations

import json
from pathlib import Path

from reconcile.dataset import _mentions_from, _relationships_from
from reconcile.embeddings import make_embedder
from reconcile.resolution.features import FeatureContext
from reconcile.resolution.scorer import WeightedRuleScorer, embedding_only_prob

REAL = Path(__file__).parent / "real"


def main():
    graph = json.loads((REAL / "graph.json").read_text())
    labels = json.loads((REAL / "labels.json").read_text())
    mentions = _mentions_from(graph["mentions"])
    relationships = _relationships_from(graph["relationships"])
    name = {m.id: m.name for m in mentions}
    ctx = FeatureContext.build(mentions, relationships, embedder=make_embedder())
    scorer = WeightedRuleScorer()

    def show(category, title):
        rows = [p for p in labels if p["category"] == category]
        print(f"\n## {title}  ({len(rows)} pairs)")
        for p in rows[:12]:
            f = ctx.features(p["a"], p["b"])
            emb = embedding_only_prob(f.embedding_cosine)
            rel = scorer.score(f)[0]
            print(f"  [{p['label']:^9}] {name[p['a']]:<22} ~ {name[p['b']]:<28} "
                  f"name={f.name_sim:.2f} shared_contacts={f.raw_shared_neighbors} "
                  f"emb_p={emb:.2f} rel_p={rel:.2f}")

    show("variant_link", "Company call-mention -> its account (gold: SAME)")
    show("person_collision", "Same name, different company (gold: DIFFERENT)")
    show("account_pair", "Distinct accounts, incl. ones sharing a partner/rep (gold: DIFFERENT)")


if __name__ == "__main__":
    main()
