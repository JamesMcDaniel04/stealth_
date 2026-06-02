"""Confidence banding — auto-merge above X, auto-reject below Y, human review between."""

from __future__ import annotations

from reconcile.models import Band, PairDecision


def band_for_score(score: float, auto_merge: float, auto_reject: float) -> Band:
    if score >= auto_merge:
        return Band.AUTO_MERGE
    if score <= auto_reject:
        return Band.AUTO_REJECT
    return Band.REVIEW


def band_decisions(
    scores: dict[tuple[str, str], float],
    auto_merge: float,
    auto_reject: float,
    contributions: dict[tuple[str, str], dict[str, float]] | None = None,
) -> list[PairDecision]:
    contributions = contributions or {}
    out = []
    for (a, b), score in sorted(scores.items()):
        out.append(
            PairDecision(
                a=a,
                b=b,
                score=score,
                band=band_for_score(score, auto_merge, auto_reject),
                evidence=contributions.get((a, b), {}),
            )
        )
    return out
