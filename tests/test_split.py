"""Reversible split: edge re-attachment, new stable ids, and a change event."""

from __future__ import annotations

from reconcile.graph import StubGraphStore
from reconcile.models import DecisionSource, EventKind, Mention, Relationship
from reconcile.ops import Engine


def _setup_over_merged(store):
    """x and y are truly the same; z gets wrongly merged in by a shared name/anchor."""
    engine = Engine(store=store, graph=StubGraphStore(), embedder=__import__(
        "reconcile.embeddings", fromlist=["StubEmbedder"]).StubEmbedder())
    mentions = [
        Mention(id="x", name="Globex", entity_type="Company", attributes={"domain": "globex.com"}),
        Mention(id="y", name="Globex", entity_type="Company", attributes={"domain": "globex.com"}),
        Mention(id="z", name="Globex", entity_type="Company", attributes={"domain": "globex.com"}),
    ]
    rels = [
        Relationship(src="x", dst="n-east", edge_type="LOCATED_IN"),
        Relationship(src="z", dst="n-west", edge_type="LOCATED_IN"),
    ]
    engine.ingest(mentions + [
        Mention(id="n-east", name="East Office", entity_type="Location"),
        Mention(id="n-west", name="West Office", entity_type="Location"),
    ], rels)
    engine.resolve()
    return engine


def test_split_separates_and_mints_new_id(store):
    engine = _setup_over_merged(store)
    assert engine.same_cluster("x", "z")  # wrongly merged
    old_cluster_id = engine.cluster_id_of("z")

    result = engine.split("x", "z", source=DecisionSource.HUMAN)

    assert not engine.same_cluster("x", "z")
    # the larger surviving cluster keeps the stable id; z's cluster gets a fresh one
    assert engine.cluster_id_of("x") == old_cluster_id
    assert engine.cluster_id_of("z") != old_cluster_id

    # a SPLIT change event records the lineage old_id -> [new ids]
    split_events = [e for e in result.events if e.kind is EventKind.SPLIT]
    assert split_events
    ev = split_events[0]
    assert old_cluster_id in ev.old_ids
    assert engine.cluster_id_of("z") in ev.new_ids


def test_split_reattaches_edges_to_correct_cluster(store):
    engine = _setup_over_merged(store)
    engine.split("x", "z", source=DecisionSource.HUMAN)

    proj = engine.graph.read_projection()
    edges = engine.graph.resolved_relationships()
    cx, cz = engine.cluster_id_of("x"), engine.cluster_id_of("z")

    # z's western office edge now hangs off z's cluster, not x's
    assert (cz, "LOCATED_IN", engine.cluster_id_of("n-west")) in edges
    assert (cx, "LOCATED_IN", engine.cluster_id_of("n-east")) in edges
    # membership reflects the split
    assert "z" in proj[cz] and "z" not in proj[cx]
