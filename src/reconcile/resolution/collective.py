"""Collective resolution — the differentiator.

Pairwise scoring runs once; then we *propagate*: rebuild clusters from the merges
accepted so far, remap every mention's neighbors to its cluster representative, and
re-block + re-score. Merges made this round become shared neighbors next round, so
aliases that share no string and no anchor (a holdco and its parent) become
resolvable once their shared employee merges. One or two rounds is enough to show
clear lift over pairwise (the minimal Bhattacharya-Getoor idea).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from reconcile.models import ConstraintRecord, PairDecision
from reconcile.resolution.blocking import candidate_pairs
from reconcile.resolution.clustering import clusters_from
from reconcile.resolution.features import FeatureContext
from reconcile.resolution.scorer import WeightedRuleScorer


def _rep_map(clusters: list[set[str]]) -> dict[str, str]:
    rep: dict[str, str] = {}
    for grp in clusters:
        r = min(grp)
        for m in grp:
            rep[m] = r
    return rep


@dataclass
class ResolutionResult:
    clusters: list[set[str]]
    rep_map: dict[str, str]
    # collective (final) score per candidate pair
    collective_scores: dict[tuple[str, str], float]
    # round-0 pairwise score per candidate pair (neighbors NOT remapped)
    pairwise_scores: dict[tuple[str, str], float]
    contributions: dict[tuple[str, str], dict[str, float]] = field(default_factory=dict)

    def pair_score(self, a: str, b: str, *, collective: bool = True) -> float | None:
        key = tuple(sorted((a, b)))
        table = self.collective_scores if collective else self.pairwise_scores
        return table.get(key)  # type: ignore[arg-type]


class CollectiveResolver:
    def __init__(
        self,
        ctx: FeatureContext,
        scorer: WeightedRuleScorer | None = None,
        merge_threshold: float = 0.55,
        max_iters: int = 3,
    ):
        self.ctx = ctx
        self.scorer = scorer or WeightedRuleScorer()
        self.merge_threshold = merge_threshold
        self.max_iters = max_iters

    def resolve(self, constraints: list[ConstraintRecord] | None = None) -> ResolutionResult:
        constraints = constraints or []
        mentions = list(self.ctx.mentions.values())
        members = [m.id for m in mentions]

        accepted: dict[tuple[str, str], float] = {}
        pairwise_scores: dict[tuple[str, str], float] = {}
        collective_scores: dict[tuple[str, str], float] = {}
        contributions: dict[tuple[str, str], dict[str, float]] = {}

        for it in range(self.max_iters):
            clusters = clusters_from(members, list(_as_merges(accepted)), constraints)
            rep_map = _rep_map(clusters)
            cands = candidate_pairs(mentions, self.ctx, neighbor_map=rep_map)

            new_added = False
            for a, b in cands:
                if rep_map[a] == rep_map[b]:
                    continue
                f = self.ctx.features(a, b, neighbor_map=rep_map)
                score, contrib = self.scorer.score(f)
                key = (a, b)
                collective_scores[key] = score
                contributions[key] = contrib
                if it == 0:
                    pairwise_scores[key] = score
                if score >= self.merge_threshold and key not in accepted:
                    accepted[key] = score
                    new_added = True
            if not new_added:
                break

        final = clusters_from(members, list(_as_merges(accepted)), constraints)
        return ResolutionResult(
            clusters=final,
            rep_map=_rep_map(final),
            collective_scores=collective_scores,
            pairwise_scores=pairwise_scores,
            contributions=contributions,
        )

    def decisions(
        self, result: ResolutionResult, auto_merge: float, auto_reject: float
    ) -> list[PairDecision]:
        from reconcile.resolution.bander import band_for_score

        out = []
        for (a, b), score in sorted(result.collective_scores.items()):
            out.append(
                PairDecision(
                    a=a,
                    b=b,
                    score=score,
                    band=band_for_score(score, auto_merge, auto_reject),
                    evidence=result.contributions.get((a, b), {}),
                )
            )
        return out


def _as_merges(accepted: dict[tuple[str, str], float]):
    for (a, b), s in accepted.items():
        yield (a, b, s)
