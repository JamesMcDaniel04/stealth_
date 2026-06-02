"""`Reconciler` — the in-process SDK facade.

One object that wires the decision store, graph store, and (cached, real-or-stub)
embedder behind the Engine with sensible defaults, so embedding reconcile in a
pipeline is two lines:

    from reconcile import Reconciler
    rec = Reconciler.local()                     # sqlite + in-memory graph, zero deps
    rec.ingest(mentions, relationships)
    rec.resolve()
    rec.split("acme-inc", "acme-corp")           # reversible
    rec.retract("acme-inc", "acme-corp")         # undo

Use `Reconciler()` to pick up configured Postgres/Neo4j/OpenAI from the environment.
"""

from __future__ import annotations

from typing import Any

from reconcile.embeddings import Embedder
from reconcile.graph import make_graph_store
from reconcile.models import (
    ChangeEvent,
    Cluster,
    DecisionSource,
    Mention,
    PairDecision,
    Relationship,
)
from reconcile.ops import Engine, ResolveResult
from reconcile.store import DecisionStore

MentionLike = Mention | dict[str, Any]
RelationshipLike = Relationship | dict[str, Any]


def _to_mention(m: MentionLike) -> Mention:
    if isinstance(m, Mention):
        return m
    return Mention(
        id=m["id"],
        name=m["name"],
        entity_type=m.get("type", m.get("entity_type", "Entity")),
        attributes={k: str(v) for k, v in (m.get("attributes") or {}).items()},
        source=m.get("source", ""),
    )


def _to_relationship(r: RelationshipLike) -> Relationship:
    if isinstance(r, Relationship):
        return r
    return Relationship(src=r["src"], dst=r["dst"], edge_type=r.get("type", r.get("edge_type", "RELATES_TO")))


class Reconciler:
    def __init__(
        self,
        database_url: str | None = None,
        graph: str = "auto",
        embedder: Embedder | None = None,
        create: bool = True,
    ):
        self.store = DecisionStore(url=database_url, create=create)
        self.graph, self.graph_kind = make_graph_store(graph)
        self.engine = Engine(store=self.store, graph=self.graph, embedder=embedder)

    @classmethod
    def local(cls, database_url: str = "sqlite:///./reconcile.db") -> "Reconciler":
        """Zero-dependency local instance: SQLite + in-memory graph + stub embedder."""
        from reconcile.embeddings import StubEmbedder

        return cls(database_url=database_url, graph="stub", embedder=StubEmbedder())

    # ---- lifecycle ---------------------------------------------------------
    def ingest(
        self, mentions: list[MentionLike], relationships: list[RelationshipLike] | None = None
    ) -> None:
        self.engine.ingest(
            [_to_mention(m) for m in mentions],
            [_to_relationship(r) for r in (relationships or [])],
        )

    async def ingest_text(self, name: str, text: str, group_id: str = "reconcile") -> ResolveResult:
        """Extract free text via Graphiti (Claude) then ingest + resolve. Needs keys."""
        from reconcile.graph.graphiti_ingest import ingest_text

        return await ingest_text(self.engine, name, text, group_id)

    def resolve(self) -> ResolveResult:
        return self.engine.resolve()

    # ---- decisions ---------------------------------------------------------
    def review_queue(self) -> list[PairDecision]:
        return self.engine.review_queue()

    def submit_decision(
        self, a: str, b: str, same: bool, evidence: dict | None = None
    ) -> ResolveResult:
        return self.engine.submit_decision(
            a, b, same=same, source=DecisionSource.HUMAN, evidence=evidence
        )

    def split(self, a: str, b: str, evidence: dict | None = None) -> ResolveResult:
        return self.engine.split(a, b, source=DecisionSource.HUMAN, evidence=evidence)

    def retract(self, a: str, b: str) -> ResolveResult:
        return self.engine.retract(a, b)

    # ---- queries -----------------------------------------------------------
    def clusters(self) -> list[Cluster]:
        return self.engine.clusters()

    def events(self) -> list[ChangeEvent]:
        return self.store.get_events()

    def cluster_id_of(self, mention_id: str) -> str | None:
        return self.engine.cluster_id_of(mention_id)

    def same_cluster(self, a: str, b: str) -> bool:
        return self.engine.same_cluster(a, b)

    def close(self) -> None:
        self.graph.close()
