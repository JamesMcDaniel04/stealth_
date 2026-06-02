"""Phase 1 gate: does collective resolution beat embedding-only on the hard cases?

Scores each labeled pair three ways and sweeps the decision threshold *per method*
(so the embedding-only baseline gets its best possible threshold — a fair fight),
then reports precision/recall/F1 for the "same" class. Collective should win.
"""

from __future__ import annotations

import sys
from pathlib import Path

from reconcile.dataset import load_dataset
from reconcile.embeddings import StubEmbedder
from reconcile.resolution.collective import CollectiveResolver
from reconcile.resolution.features import FeatureContext
from reconcile.resolution.scorer import WeightedRuleScorer, embedding_only_prob

HARD_CASES = Path(__file__).parent / "hard_cases.yaml"


def _best_f1(scored: list[tuple[float, bool]]) -> tuple[float, float, float, float]:
    """Sweep thresholds; return (threshold, precision, recall, f1) maximizing f1."""
    thresholds = sorted({s for s, _ in scored} | {0.0, 1.0})
    best = (0.5, 0.0, 0.0, 0.0)
    for t in thresholds:
        tp = sum(1 for s, g in scored if s >= t and g)
        fp = sum(1 for s, g in scored if s >= t and not g)
        fn = sum(1 for s, g in scored if s < t and g)
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        if f1 > best[3]:
            best = (t, prec, rec, f1)
    return best


def run(path: Path = HARD_CASES) -> dict[str, tuple[float, float, float, float]]:
    ds = load_dataset(path)
    ctx = FeatureContext.build(ds.mentions, ds.relationships, embedder=StubEmbedder())
    scorer = WeightedRuleScorer()
    result = CollectiveResolver(ctx, scorer).resolve()

    rows = []
    emb_scored, pw_scored, col_scored = [], [], []
    for p in ds.pairs:
        f0 = ctx.features(p.a, p.b)  # round-0 (identity neighbor map)
        fc = ctx.features(p.a, p.b, neighbor_map=result.rep_map)
        emb = embedding_only_prob(f0.embedding_cosine)
        pw = scorer.score(f0)[0]
        col = scorer.score(fc)[0]
        emb_scored.append((emb, p.gold_same))
        pw_scored.append((pw, p.gold_same))
        col_scored.append((col, p.gold_same))
        rows.append((p, emb, pw, col))

    metrics = {
        "embedding_only": _best_f1(emb_scored),
        "pairwise_relational": _best_f1(pw_scored),
        "collective": _best_f1(col_scored),
    }

    _print_report(rows, metrics)
    return metrics


def _print_report(rows, metrics) -> None:
    print("\n=== Per-pair scores (prob 'same') ===")
    print(f"{'pair':<34} {'gold':<10} {'emb':>6} {'pair':>6} {'coll':>6}")
    for p, emb, pw, col in rows:
        pair = f"{p.a} / {p.b}"
        flag = ""
        if (col >= 0.5) != p.gold_same:
            flag = "  <- collective wrong"
        elif (emb >= 0.5) != p.gold_same:
            flag = "  <- emb-only wrong (collective right)"
        print(f"{pair:<34} {p.label:<10} {emb:>6.2f} {pw:>6.2f} {col:>6.2f}{flag}")

    print("\n=== Best-threshold metrics on hard cases (positive class = 'same') ===")
    print(f"{'method':<22} {'thr':>5} {'prec':>6} {'rec':>6} {'f1':>6}")
    for name, (t, pr, rc, f1) in metrics.items():
        print(f"{name:<22} {t:>5.2f} {pr:>6.2f} {rc:>6.2f} {f1:>6.2f}")

    emb_f1 = metrics["embedding_only"][3]
    col_f1 = metrics["collective"][3]
    lift = col_f1 - emb_f1
    print(f"\ncollective F1 - embedding-only F1 = {lift:+.2f}")
    gate = "PASS" if lift >= 0.10 else "FAIL"
    print(f"Phase 1 gate (collective materially beats embedding-only): {gate}")


if __name__ == "__main__":
    metrics = run()
    lift = metrics["collective"][3] - metrics["embedding_only"][3]
    sys.exit(0 if lift >= 0.10 else 1)
