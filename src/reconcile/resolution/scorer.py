"""Transparent weighted-rule scorer.

Deliberately interpretable (not a black box): the score is a weighted sum of
features passed through a logistic squash, and every call returns the per-feature
contribution so the review queue can explain *why* a pair was merged or kept apart.

Weights encode the thesis: anchor agreement and shared relationship neighborhoods
are strong "same" signals; an anchor *conflict* is a near-veto "different" signal
that overrides high string/embedding similarity (the Acme Inc / Acme Corp case).
"""

from __future__ import annotations

import math

from reconcile.resolution.features import PairFeatures

# Transparent, hand-tuned weights. Positive pushes toward "same entity".
#
# Relational evidence (shared neighbors) is weighted *above* string/embedding
# similarity: that's the thesis. edge_type_overlap is deliberately zero — within a
# single entity type it is near-constant (every Company shares relation types) and
# only injects noise that causes collective over-merging.
DEFAULT_WEIGHTS: dict[str, float] = {
    "bias": -2.5,  # prior: assume different until evidence says otherwise
    "name_sim": 2.0,
    "embedding_cosine": 1.5,
    "jaccard_neighbors": 0.5,  # weak on its own (two 1-neighbor nodes score 1.0)
    "adamic_adar": 3.0,  # the real relational signal: discriminative shared neighbors
    "edge_type_overlap": 0.0,  # noise within a type; kept for transparency only
    "anchor_agreement": 4.0,  # strong: shared authoritative id / domain / email
    "anchor_conflict": -6.0,  # near-veto: conflicting id overrides name/embedding
}


def _sigmoid(z: float) -> float:
    if z < -60:
        return 0.0
    if z > 60:
        return 1.0
    return 1.0 / (1.0 + math.exp(-z))


class WeightedRuleScorer:
    def __init__(self, weights: dict[str, float] | None = None):
        self.weights = {**DEFAULT_WEIGHTS, **(weights or {})}

    def score(self, f: PairFeatures) -> tuple[float, dict[str, float]]:
        """Return (calibrated probability, per-feature contribution to the logit)."""
        w = self.weights
        contrib = {"bias": w["bias"]}
        for name, value in f.as_dict().items():
            contrib[name] = w.get(name, 0.0) * value
        z = sum(contrib.values())
        return _sigmoid(z), contrib


def embedding_only_prob(embedding_cosine: float) -> float:
    """Baseline-to-beat: identity decided by embedding similarity alone.

    Maps cosine in [0,1] through a sharp logistic centered at 0.5 so the baseline
    behaves like a typical embedding-threshold deduper.
    """
    return _sigmoid(12.0 * (embedding_cosine - 0.5))
