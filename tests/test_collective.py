"""Collective resolution: clusters the hard cases correctly and beats pairwise."""

from __future__ import annotations

from reconcile.resolution.collective import CollectiveResolver


def _same_cluster(result, a, b) -> bool:
    return result.rep_map[a] == result.rep_map[b]


def test_collective_clusters_hard_cases_correctly(feature_ctx):
    r = CollectiveResolver(feature_ctx).resolve()

    # SAME entities land together
    assert _same_cluster(r, "ibm-long", "ibm-short")
    assert _same_cluster(r, "fb", "meta")
    assert _same_cluster(r, "globex-1", "globex-2")
    assert _same_cluster(r, "stark-1", "stark-2")
    assert _same_cluster(r, "jsmith-acme", "jsmith-abbrev")

    # DIFFERENT entities stay apart despite look-alike strings
    assert not _same_cluster(r, "acme-inc", "acme-corp")
    assert not _same_cluster(r, "jsmith-acme", "jsmith-initech")
    assert not _same_cluster(r, "initech", "umbrella")


def test_collective_beats_pairwise_on_alias(feature_ctx):
    """wayne/gotham share no string and no anchor — only propagation resolves them."""
    from reconcile.resolution.scorer import WeightedRuleScorer

    scorer = WeightedRuleScorer()
    r = CollectiveResolver(feature_ctx, scorer).resolve()

    # round-0 (identity neighbors): pairwise has nothing to go on
    pairwise = scorer.score(feature_ctx.features("wayne", "gotham"))[0]
    # after propagation (neighbors remapped to merged clusters): resolvable
    collective = scorer.score(feature_ctx.features("wayne", "gotham", neighbor_map=r.rep_map))[0]

    assert pairwise < 0.5  # pairwise can't see it
    assert collective >= 0.55  # collective can
    assert _same_cluster(r, "wayne", "gotham")
    assert _same_cluster(r, "lucius-a", "lucius-b")  # the enabling merge


def test_coworkers_sharing_only_a_hub_do_not_merge(store):
    """Two people sharing only a high-degree employer must NOT be merged.

    A single non-discriminative shared neighbor (a company with many employees) is
    weak evidence — Adamic-Adar down-weights it. Guards against collective over-merge.
    """
    from reconcile.embeddings import StubEmbedder
    from reconcile.graph import StubGraphStore
    from reconcile.models import Mention, Relationship
    from reconcile.ops import Engine

    engine = Engine(store=store, graph=StubGraphStore(), embedder=StubEmbedder())
    mentions = [
        Mention(id="co", name="Acme", entity_type="Company", attributes={"domain": "acme.com"}),
        Mention(id="p1", name="Jane Doe", entity_type="Person"),
        Mention(id="p2", name="Carol Reed", entity_type="Person"),
        Mention(id="p3", name="Dan Park", entity_type="Person"),
    ]
    rels = [Relationship(src="co", dst=p, edge_type="EMPLOYS") for p in ("p1", "p2", "p3")]
    engine.ingest(mentions, rels)
    engine.resolve()
    assert not engine.same_cluster("p1", "p2")
    assert not engine.same_cluster("p1", "p3")


def test_decisions_are_banded(feature_ctx):
    r = CollectiveResolver(feature_ctx).resolve()
    decisions = CollectiveResolver(feature_ctx).decisions(r, auto_merge=0.8, auto_reject=0.3)
    assert decisions
    bands = {d.band.value for d in decisions}
    assert "auto_merge" in bands
    assert "auto_reject" in bands
