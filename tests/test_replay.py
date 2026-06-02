"""THE moat test: a human split survives re-ingestion via constraint replay.

If this passes, reconcile does the one thing Graphiti can't: a human decision is
never silently overwritten by the next extraction. Written before the implementation.
"""

from __future__ import annotations

from reconcile.embeddings import StubEmbedder
from reconcile.graph import StubGraphStore
from reconcile.models import DecisionSource, Mention, Relationship
from reconcile.ops import Engine


def _acme(mid: str, domain: str = "acme.com") -> Mention:
    return Mention(id=mid, name="Acme", entity_type="Company", attributes={"domain": domain})


def test_human_split_persists_through_reingestion(store):
    engine = Engine(store=store, graph=StubGraphStore(), embedder=StubEmbedder())

    # Two identical "Acme" mentions — the resolver merges them by default.
    engine.ingest([_acme("m1"), _acme("m2")], [])
    result = engine.resolve()
    assert engine.same_cluster("m1", "m2"), "identical mentions should auto-merge first"

    # A human reviews the evidence and declares them distinct: this is a SPLIT.
    engine.split("m1", "m2", source=DecisionSource.HUMAN, evidence={"reason": "different legal entity"})
    assert not engine.same_cluster("m1", "m2"), "split should separate them immediately"

    # New extraction arrives: a third identical "Acme" that strongly matches both.
    engine.ingest([_acme("m3")], [Relationship(src="m3", dst="m1", edge_type="ALIAS_OF")])
    engine.resolve()  # re-resolution replays persisted constraints before writing

    # The moat: m1 and m2 are STILL separate, with zero manual re-fixing.
    assert not engine.same_cluster("m1", "m2"), "human cannot-link must survive re-ingestion"


def test_replayed_constraint_is_loaded_from_store(store):
    """The constraint lives in the decision store, independent of any in-memory state."""
    engine = Engine(store=store, graph=StubGraphStore(), embedder=StubEmbedder())
    engine.ingest([_acme("m1"), _acme("m2")], [])
    engine.resolve()
    engine.split("m1", "m2", source=DecisionSource.HUMAN)

    # A brand-new Engine over the same store must honor the split.
    fresh = Engine(store=store, graph=StubGraphStore(), embedder=StubEmbedder())
    fresh.resolve()
    assert not fresh.same_cluster("m1", "m2")
