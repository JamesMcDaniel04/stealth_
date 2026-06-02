"""Constraint retraction / undo — true two-way reversibility."""

from __future__ import annotations

from reconcile.embeddings import StubEmbedder
from reconcile.graph import StubGraphStore
from reconcile.models import DecisionSource, Mention
from reconcile.ops import Engine


def _acme(mid: str) -> Mention:
    return Mention(id=mid, name="Acme", entity_type="Company", attributes={"domain": "acme.com"})


def _engine(store):
    return Engine(store=store, graph=StubGraphStore(), embedder=StubEmbedder())


def test_undo_split_remerges(store):
    engine = _engine(store)
    engine.ingest([_acme("m1"), _acme("m2")], [])
    engine.resolve()
    assert engine.same_cluster("m1", "m2")

    engine.split("m1", "m2", source=DecisionSource.HUMAN)
    assert not engine.same_cluster("m1", "m2")

    engine.retract("m1", "m2")  # undo
    assert engine.same_cluster("m1", "m2"), "retracting the split should let them re-merge"


def test_undo_persists_through_reresolve(store):
    engine = _engine(store)
    engine.ingest([_acme("m1"), _acme("m2")], [])
    engine.resolve()
    engine.split("m1", "m2", source=DecisionSource.HUMAN)
    engine.retract("m1", "m2")
    engine.resolve()  # re-resolve must not resurrect the retracted constraint
    assert engine.same_cluster("m1", "m2")
    assert engine.store.get_constraints(active_only=True) == []


def test_latest_human_decision_wins(store):
    engine = _engine(store)
    engine.ingest([_acme("m1"), _acme("m2")], [])
    engine.resolve()

    engine.submit_decision("m1", "m2", same=False, source=DecisionSource.HUMAN)  # split
    assert not engine.same_cluster("m1", "m2")

    engine.submit_decision("m1", "m2", same=True, source=DecisionSource.HUMAN)  # flip back
    assert engine.same_cluster("m1", "m2")

    # exactly one active constraint survives the flip (the latest)
    active = engine.store.get_constraints(active_only=True)
    assert len(active) == 1
    assert active[0].kind.value == "must_link"
