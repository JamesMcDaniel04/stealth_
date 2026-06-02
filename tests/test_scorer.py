"""Feature computation + scorer evidence breakdown."""

from __future__ import annotations

from reconcile.resolution.scorer import WeightedRuleScorer


def _feat(ctx, a, b):
    return ctx.features(a, b)


def test_anchor_conflict_overrides_name_similarity(feature_ctx):
    """Acme Inc vs Acme Corp: high name sim but conflicting external_id => 'different'."""
    f = _feat(feature_ctx, "acme-inc", "acme-corp")
    assert f.name_sim > 0.6  # they look similar by string
    assert f.anchor_conflict == 1.0
    prob, contrib = WeightedRuleScorer().score(f)
    assert prob < 0.1
    # the conflict term is the dominant negative contribution
    assert contrib["anchor_conflict"] < -3.0


def test_shared_anchor_beats_low_name_sim(feature_ctx):
    """IBM acronym vs full name: low name sim but same id + shared neighbors => 'same'."""
    f = _feat(feature_ctx, "ibm-long", "ibm-short")
    assert f.anchor_agreement == 1.0
    assert f.jaccard_neighbors == 1.0
    prob, _ = WeightedRuleScorer().score(f)
    assert prob > 0.9


def test_evidence_breakdown_sums_to_logit(feature_ctx):
    f = _feat(feature_ctx, "ibm-long", "ibm-short")
    prob, contrib = WeightedRuleScorer().score(f)
    assert "bias" in contrib and "anchor_agreement" in contrib
    # every feature key is explained
    for k in f.as_dict():
        assert k in contrib


def test_unrelated_controls_score_low(feature_ctx):
    for a, b in [("acme-inc", "ibm-long"), ("fb", "initech"), ("stark-1", "umbrella")]:
        prob, _ = WeightedRuleScorer().score(_feat(feature_ctx, a, b))
        assert prob < 0.2
