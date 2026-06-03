"""Phase 7: does collective resolution beat embedding-only on REAL CRM data?

Two metrics:
  1. Decisions at a realistic threshold (0.5) on the real hard cases: how many messy company
     call-mentions get linked to their account, and how many same-name/different-company people
     get (correctly) kept apart. Relational features should win both.
  2. Pairwise P/R/F1 over all labeled pairs (variants + account pairs + person collisions),
     reusing the synthetic harness's `_best_f1`, plus a by-category error breakdown.

Uses the real embedder when OPENAI_API_KEY is set, else the offline stub (preliminary:
the stub understates a semantic baseline on acronyms — re-run with a key for the
definitive embedding-only baseline).
"""

from __future__ import annotations

import json
from pathlib import Path

from eval.run_eval import _best_f1
from reconcile.dataset import _mentions_from, _relationships_from
from reconcile.embeddings import make_embedder
from reconcile.resolution.collective import CollectiveResolver
from reconcile.resolution.features import FeatureContext
from reconcile.resolution.scorer import WeightedRuleScorer, embedding_only_prob

REAL = Path(__file__).parent / "real"


def _load():
    graph = json.loads((REAL / "graph.json").read_text())
    labels = json.loads((REAL / "labels.json").read_text())
    mentions = _mentions_from(graph["mentions"])
    relationships = _relationships_from(graph["relationships"])
    return mentions, relationships, labels


def run():
    mentions, relationships, labels = _load()
    embedder = make_embedder()
    using_real = type(embedder).__name__ == "OpenAIEmbedder"
    ctx = FeatureContext.build(mentions, relationships, embedder=embedder)
    scorer = WeightedRuleScorer()
    result = CollectiveResolver(ctx, scorer).resolve()

    def emb_prob(a, b):
        return embedding_only_prob(ctx.features(a, b).embedding_cosine)

    def pairwise_prob(a, b):
        return scorer.score(ctx.features(a, b))[0]

    def collective_prob(a, b):
        return scorer.score(ctx.features(a, b, neighbor_map=result.rep_map))[0]

    methods = {"embedding_only": emb_prob, "pairwise": pairwise_prob, "collective": collective_prob}

    print(f"\nembedder: {embedder.model_id}"
          f"{'' if using_real else '   (PRELIMINARY — stub; re-run with OPENAI_API_KEY)'}")

    name_of = {m.id: m.name for m in mentions}

    # ---- Metric 1: behavior at a realistic operating threshold (0.5) ------
    # The two real hard cases: (a) link a messy company call-mention to its account,
    # (b) keep same-name-different-company people apart. Reported as decisions at 0.5.
    print("\n=== Metric 1: decisions at threshold 0.5 on the real hard cases ===")
    links = [p for p in labels if p["category"] == "variant_link"]
    collisions = [p for p in labels if p["category"] == "person_collision"]
    print(f"{'method':<18} {'variant links made':>20} {'collisions kept apart':>24}")
    linkcount = {}
    for mname, fn in methods.items():
        made = sum(1 for p in links if fn(p["a"], p["b"]) >= 0.5)
        apart = sum(1 for p in collisions if fn(p["a"], p["b"]) < 0.5)
        linkcount[mname] = made
        print(f"{mname:<18} {f'{made}/{len(links)}':>20} {f'{apart}/{len(collisions)}':>24}")
    print("  (variant link example: '" + name_of[links[0]['a']] + "' -> '"
          + name_of[links[0]['b']] + "')")

    # ---- Metric 2: pairwise P/R/F1 over all labeled pairs -----------------
    print("\n=== Metric 2: pairwise resolution P/R/F1 (positive = 'same') ===")
    scored = {m: [] for m in methods}
    for p in labels:
        gold_same = p["label"] == "same"
        for mname, fn in methods.items():
            scored[mname].append((fn(p["a"], p["b"]), gold_same))
    print(f"{'method':<18} {'thr':>5} {'prec':>6} {'rec':>6} {'f1':>6}")
    f1 = {}
    for mname in methods:
        t, pr, rc, fr = _best_f1(scored[mname])
        f1[mname] = fr
        print(f"{mname:<18} {t:>5.2f} {pr:>6.2f} {rc:>6.2f} {fr:>6.2f}")

    # ---- per-category error counts (at a fixed 0.5 threshold) -------------
    print("\n=== Errors by category at threshold 0.5 ===")
    cats = sorted({p["category"] for p in labels})
    print(f"{'category':<18} " + "  ".join(f"{m:>14}" for m in methods))
    for cat in cats:
        rows = [p for p in labels if p["category"] == cat]
        cells = []
        for fn in methods.values():
            wrong = sum(1 for p in rows if (fn(p["a"], p["b"]) >= 0.5) != (p["label"] == "same"))
            cells.append(f"{wrong}/{len(rows):>2} wrong")
        print(f"{cat:<18} " + "  ".join(f"{c:>14}" for c in cells))

    lift = f1["collective"] - f1["embedding_only"]
    link_lift = linkcount["collective"] - linkcount["embedding_only"]
    print(f"\nHEADLINE: collective F1 - embedding-only F1 = {lift:+.2f}; "
          f"variant links made {linkcount['collective']}/{len(links)} vs "
          f"{linkcount['embedding_only']}/{len(links)} (+{link_lift})")
    passed = lift >= 0.10 or link_lift >= 2
    print(f"Kill-criterion (collective materially beats embedding-only on real data): "
          f"{'PASS' if passed else 'FAIL'}")
    return {"f1": f1, "links": linkcount, "n_variants": len(links),
            "using_real_embedder": using_real}


if __name__ == "__main__":
    run()
