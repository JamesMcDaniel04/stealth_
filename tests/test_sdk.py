"""SDK facade: the full lifecycle in a few lines, dict-friendly inputs."""

from __future__ import annotations

import uuid

import pytest

from reconcile import Reconciler


@pytest.fixture
def rec(tmp_path):
    r = Reconciler.local(database_url=f"sqlite:///{tmp_path / (uuid.uuid4().hex + '.db')}")
    yield r
    r.close()


def test_sdk_resolve_split_retract_roundtrip(rec):
    rec.ingest(
        mentions=[
            {"id": "m1", "name": "Acme", "type": "Company", "attributes": {"domain": "acme.com"}},
            {"id": "m2", "name": "Acme", "type": "Company", "attributes": {"domain": "acme.com"}},
        ],
        relationships=[],
    )
    rec.resolve()
    assert rec.same_cluster("m1", "m2")

    rec.split("m1", "m2", evidence={"reason": "distinct"})
    assert not rec.same_cluster("m1", "m2")
    assert any(e.kind.value == "split" for e in rec.events())

    rec.retract("m1", "m2")
    assert rec.same_cluster("m1", "m2")


def test_sdk_accepts_model_objects(rec):
    from reconcile import Mention, Relationship

    rec.ingest(
        [Mention(id="a", name="X", entity_type="Company", attributes={"domain": "x.com"}),
         Mention(id="b", name="X", entity_type="Company", attributes={"domain": "x.com"})],
        [Relationship(src="a", dst="b", edge_type="ALIAS_OF")],
    )
    rec.resolve()
    assert rec.same_cluster("a", "b")
