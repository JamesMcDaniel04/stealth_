"""Constrained clustering honors must-link / cannot-link with the right precedence."""

from __future__ import annotations

from reconcile.models import ConstraintKind, ConstraintRecord, DecisionSource
from reconcile.resolution.clustering import ConstrainedClusterer, clusters_from


def _cl(kind, a, b, source=DecisionSource.MACHINE):
    return ConstraintRecord(kind=kind, a=a, b=b, source=source)


def test_plain_merges_form_clusters():
    groups = clusters_from(["a", "b", "c", "d"], [("a", "b", 0.9), ("b", "c", 0.8)])
    sizes = sorted(len(g) for g in groups)
    assert sizes == [1, 3]  # {a,b,c} and {d}


def test_cannot_link_blocks_a_merge():
    groups = clusters_from(
        ["a", "b"],
        merges=[("a", "b", 0.99)],
        constraints=[_cl(ConstraintKind.CANNOT_LINK, "a", "b", DecisionSource.HUMAN)],
    )
    assert sorted(len(g) for g in groups) == [1, 1]


def test_cannot_link_is_transitive_through_a_cluster():
    # a-b merge, then a cannot-link to c must keep c out even if c wants to join b
    groups = clusters_from(
        ["a", "b", "c"],
        merges=[("a", "b", 0.99), ("b", "c", 0.99)],
        constraints=[_cl(ConstraintKind.CANNOT_LINK, "a", "c")],
    )
    # a,b together; c separate (its merge into {a,b} is forbidden via a)
    by_size = sorted((sorted(g) for g in groups), key=len)
    assert ["c"] in [sorted(g) for g in groups]
    assert any(set(g) == {"a", "b"} for g in groups)
    assert len(by_size) == 2


def test_must_link_forces_merge():
    groups = clusters_from(
        ["a", "b"],
        merges=[],
        constraints=[_cl(ConstraintKind.MUST_LINK, "a", "b", DecisionSource.HUMAN)],
    )
    assert len(groups) == 1


def test_cannot_link_precedence_over_machine_merge():
    """The defining replay behavior: a human cannot-link beats a confident machine merge."""
    groups = clusters_from(
        ["x", "y"],
        merges=[("x", "y", 1.0)],
        constraints=[_cl(ConstraintKind.CANNOT_LINK, "x", "y", DecisionSource.HUMAN)],
    )
    assert sorted(len(g) for g in groups) == [1, 1]


def test_clusterer_would_violate_query():
    c = ConstrainedClusterer(["a", "b", "c"])
    c.union("a", "b")
    c.cannot_link("a", "c")
    assert c.would_violate("b", "c") is True
    assert c.would_violate("a", "b") is False
