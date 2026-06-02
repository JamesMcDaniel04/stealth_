"""Live Neo4j projection round-trip. Requires `make up`. Run: pytest -m integration."""

from __future__ import annotations

import uuid

import pytest

from reconcile.embeddings import StubEmbedder
from reconcile.models import DecisionSource, Mention, Relationship
from reconcile.ops import Engine
from reconcile.store import DecisionStore

pytestmark = pytest.mark.integration


@pytest.fixture
def neo4j_store():
    try:
        from reconcile.graph.neo4j_store import Neo4jStore

        store = Neo4jStore()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Neo4j not reachable: {exc}")
    store.clear()
    yield store
    store.clear()
    store.close()


def test_projection_roundtrip_and_split(tmp_path, neo4j_store):
    ds = DecisionStore(url=f"sqlite:///{tmp_path / (uuid.uuid4().hex + '.db')}", create=True)
    engine = Engine(store=ds, graph=neo4j_store, embedder=StubEmbedder())

    engine.ingest(
        [
            Mention(id="a", name="Acme Inc", entity_type="Company",
                    attributes={"domain": "acme.com", "external_id": "SF-1"}),
            Mention(id="b", name="Acme Corp", entity_type="Company",
                    attributes={"domain": "acme-corp.io", "external_id": "SF-2"}),
            Mention(id="p", name="Jane", entity_type="Person"),
        ],
        [Relationship(src="a", dst="p", edge_type="EMPLOYS")],
    )
    engine.resolve()

    # the resolved layer exists in Neo4j and keeps the two Acmes apart
    proj = neo4j_store.read_projection()
    assert not engine.same_cluster("a", "b")
    assert any(members == {"a"} for members in proj.values())

    # force-merge, then split, and confirm the live projection reflects the split
    engine.submit_decision("a", "b", same=True, source=DecisionSource.MACHINE)
    assert engine.same_cluster("a", "b")
    engine.split("a", "b", source=DecisionSource.HUMAN)
    proj = neo4j_store.read_projection()
    ca = engine.cluster_id_of("a")
    assert "b" not in proj[ca]
    # the EMPLOYS edge re-attached under a's resolved cluster
    edges = neo4j_store.resolved_relationships()
    assert (ca, "EMPLOYS", engine.cluster_id_of("p")) in edges
