"""End-to-end API flow: ingest -> resolve -> split -> persists."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

import reconcile.api.app as app_module
from reconcile.embeddings import StubEmbedder
from reconcile.graph import StubGraphStore
from reconcile.ops import Engine
from reconcile.store import DecisionStore


@pytest.fixture
def client(tmp_path):
    url = f"sqlite:///{tmp_path / (uuid.uuid4().hex + '.db')}"
    engine = Engine(
        store=DecisionStore(url=url, create=True),
        graph=StubGraphStore(),
        embedder=StubEmbedder(),
    )
    app_module._engine = engine  # inject an isolated engine
    yield TestClient(app_module.app)
    app_module._engine = None


def test_full_api_flow(client):
    client.post("/ingest", json={
        "mentions": [
            {"id": "m1", "name": "Acme", "type": "Company", "attributes": {"domain": "acme.com"}},
            {"id": "m2", "name": "Acme", "type": "Company", "attributes": {"domain": "acme.com"}},
        ],
        "relationships": [],
    })

    resolved = client.post("/resolve").json()
    members = {frozenset(c["members"]) for c in resolved["clusters"]}
    assert frozenset({"m1", "m2"}) in members  # auto-merged

    split = client.post(
        "/split", json={"a": "m1", "b": "m2", "evidence": {"reason": "distinct"}}
    ).json()
    members = {frozenset(c["members"]) for c in split["clusters"]}
    assert frozenset({"m1"}) in members and frozenset({"m2"}) in members
    assert any(e["kind"] == "split" for e in split["events"])

    # split persists through another resolve
    again = client.post("/resolve").json()
    members = {frozenset(c["members"]) for c in again["clusters"]}
    assert frozenset({"m1"}) in members and frozenset({"m2"}) in members

    events = client.get("/events").json()
    assert any(e["kind"] == "split" for e in events)
