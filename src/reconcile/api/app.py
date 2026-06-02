"""FastAPI service exposing the resolution lifecycle.

Endpoints:
  POST /ingest          add candidate mentions + relationships
  POST /ingest-text     extract free text via Graphiti (Claude) then ingest (needs keys)
  POST /resolve         run collective resolution (replays constraints)
  GET  /review-queue    ambiguous pairs awaiting a human decision
  POST /decisions       human merge/split decision (latest-human-decision-wins)
  POST /split           reversible split of two mentions
  POST /retract         undo a split/decision (re-resolve without the constraint)
  GET  /clusters        current resolved clusters
  GET  /events          change-event log (splits / merges)

Auth: when RECONCILE_API_TOKEN is set, every endpoint except /health requires
`Authorization: Bearer <token>`. Unset = open (local dev).
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, Header, HTTPException

from reconcile.api.schemas import (
    ClusterOut,
    DecisionRequest,
    EventOut,
    IngestRequest,
    IngestTextRequest,
    ResolveResponse,
    RetractRequest,
    ReviewItem,
    SplitRequest,
)
from reconcile.config import get_settings
from reconcile.graph import make_graph_store
from reconcile.models import Mention, Relationship
from reconcile.ops import Engine, ResolveResult
from reconcile.store import DecisionStore

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        create = get_settings().database_url.startswith("sqlite")
        store = DecisionStore(create=create)
        graph, _ = make_graph_store("auto")
        _engine = Engine(store=store, graph=graph)
    return _engine


def require_auth(authorization: str = Header(default="")) -> None:
    """Enforce a bearer token only when RECONCILE_API_TOKEN is configured."""
    token = get_settings().reconcile_api_token
    if not token:
        return
    expected = f"Bearer {token}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="invalid or missing bearer token")


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
    auth = [Depends(require_auth)]

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.post("/ingest", dependencies=auth)
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

    @app.post("/ingest-text", dependencies=auth)
    async def ingest_text(req: IngestTextRequest) -> ResolveResponse:
        from reconcile.graph.graphiti_ingest import ingest_text as _ingest_text

        result = await _ingest_text(get_engine(), req.name, req.text, req.group_id)
        return _to_resolve_response(result)

    @app.post("/resolve", dependencies=auth)
    def resolve() -> ResolveResponse:
        return _to_resolve_response(get_engine().resolve())

    @app.get("/review-queue", dependencies=auth)
    def review_queue() -> list[ReviewItem]:
        return [
            ReviewItem(a=d.a, b=d.b, score=d.score, evidence=d.evidence)
            for d in get_engine().review_queue()
        ]

    @app.post("/decisions", dependencies=auth)
    def submit_decision(req: DecisionRequest) -> ResolveResponse:
        result = get_engine().submit_decision(req.a, req.b, same=req.same, evidence=req.evidence)
        return _to_resolve_response(result)

    @app.post("/split", dependencies=auth)
    def split(req: SplitRequest) -> ResolveResponse:
        return _to_resolve_response(get_engine().split(req.a, req.b, evidence=req.evidence))

    @app.post("/retract", dependencies=auth)
    def retract(req: RetractRequest) -> ResolveResponse:
        return _to_resolve_response(get_engine().retract(req.a, req.b))

    @app.get("/clusters", dependencies=auth)
    def clusters() -> list[ClusterOut]:
        return [
            ClusterOut(cluster_id=c.cluster_id, members=sorted(c.members))
            for c in get_engine().clusters()
        ]

    @app.get("/events", dependencies=auth)
    def events() -> list[EventOut]:
        return [
            EventOut(kind=e.kind.value, old_ids=e.old_ids, new_ids=e.new_ids)
            for e in get_engine().store.get_events()
        ]

    return app


app = create_app()
