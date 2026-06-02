"""FastAPI app exposing the resolution lifecycle.

Endpoints (these back the future review-queue UI; no UI is shipped this pass):
  POST /ingest          add candidate mentions + relationships
  POST /resolve         run collective resolution (replays constraints)
  GET  /review-queue    ambiguous pairs awaiting a human decision
  POST /decisions       human merge/split decision from the queue
  POST /split           reversible split of two mentions
  GET  /clusters        current resolved clusters
  GET  /events          change-event log (splits / merges)
"""

from __future__ import annotations

from fastapi import FastAPI

from reconcile.api.schemas import (
    ClusterOut,
    DecisionRequest,
    EventOut,
    IngestRequest,
    ResolveResponse,
    ReviewItem,
    SplitRequest,
)
from reconcile.config import get_settings
from reconcile.embeddings import default_embedder
from reconcile.graph.base import GraphStore
from reconcile.graph.stub_store import StubGraphStore
from reconcile.models import Mention, Relationship
from reconcile.ops import Engine, ResolveResult
from reconcile.store import DecisionStore

_engine: Engine | None = None


def _make_graph_store() -> GraphStore:
    try:
        from reconcile.graph.neo4j_store import Neo4jStore

        return Neo4jStore()
    except Exception:  # noqa: BLE001 — fall back so the API is usable without Neo4j
        return StubGraphStore()


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        create = get_settings().database_url.startswith("sqlite")
        store = DecisionStore(create=create)
        _engine = Engine(store=store, graph=_make_graph_store(), embedder=default_embedder())
    return _engine


def _to_resolve_response(result: ResolveResult) -> ResolveResponse:
    return ResolveResponse(
        clusters=[
            ClusterOut(cluster_id=c.cluster_id, members=sorted(c.members)) for c in result.clusters
        ],
        events=[
            EventOut(kind=e.kind.value, old_ids=e.old_ids, new_ids=e.new_ids) for e in result.events
        ],
    )


def create_app() -> FastAPI:
    app = FastAPI(title="reconcile", version="0.1.0")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.post("/ingest")
    def ingest(req: IngestRequest) -> dict:
        engine = get_engine()
        mentions = [
            Mention(id=m.id, name=m.name, entity_type=m.type, attributes=m.attributes,
                    source=m.source)
            for m in req.mentions
        ]
        rels = [Relationship(src=r.src, dst=r.dst, edge_type=r.type) for r in req.relationships]
        engine.ingest(mentions, rels)
        return {"ingested_mentions": len(mentions), "ingested_relationships": len(rels)}

    @app.post("/resolve", response_model=ResolveResponse)
    def resolve() -> ResolveResponse:
        return _to_resolve_response(get_engine().resolve())

    @app.get("/review-queue", response_model=list[ReviewItem])
    def review_queue() -> list[ReviewItem]:
        return [
            ReviewItem(a=d.a, b=d.b, score=d.score, evidence=d.evidence)
            for d in get_engine().review_queue()
        ]

    @app.post("/decisions", response_model=ResolveResponse)
    def submit_decision(req: DecisionRequest) -> ResolveResponse:
        result = get_engine().submit_decision(req.a, req.b, same=req.same, evidence=req.evidence)
        return _to_resolve_response(result)

    @app.post("/split", response_model=ResolveResponse)
    def split(req: SplitRequest) -> ResolveResponse:
        result = get_engine().split(req.a, req.b, evidence=req.evidence)
        return _to_resolve_response(result)

    @app.get("/clusters", response_model=list[ClusterOut])
    def clusters() -> list[ClusterOut]:
        return [
            ClusterOut(cluster_id=c.cluster_id, members=sorted(c.members))
            for c in get_engine().clusters()
        ]

    @app.get("/events", response_model=list[EventOut])
    def events() -> list[EventOut]:
        return [
            EventOut(kind=e.kind.value, old_ids=e.old_ids, new_ids=e.new_ids)
            for e in get_engine().store.get_events()
        ]

    return app


app = create_app()
