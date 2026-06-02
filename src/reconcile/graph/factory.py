"""Graph-store selection shared by the SDK, API, and demos."""

from __future__ import annotations

from reconcile.graph.base import GraphStore
from reconcile.graph.stub_store import StubGraphStore


def make_graph_store(kind: str = "auto") -> tuple[GraphStore, str]:
    """Return (store, description). kind: "auto" | "stub" | "neo4j".

    "auto" uses live Neo4j when reachable and falls back to the in-memory store.
    """
    if kind == "stub":
        return StubGraphStore(), "in-memory"
    try:
        from reconcile.graph.neo4j_store import Neo4jStore

        return Neo4jStore(), "neo4j"
    except Exception as exc:  # noqa: BLE001 — degrade rather than crash
        if kind == "neo4j":
            raise
        return StubGraphStore(), f"in-memory (Neo4j unavailable: {type(exc).__name__})"
