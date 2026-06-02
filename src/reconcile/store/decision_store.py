"""DecisionStore — CRUD over the source-of-truth tables.

Everything the resolver needs to re-cluster from scratch lives here, so constraint
replay can run without ever reading the graph.
"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from reconcile.models import (
    ChangeEvent,
    Cluster,
    ConstraintKind,
    ConstraintRecord,
    DecisionSource,
    Mention,
    PairDecision,
    Relationship,
)
from reconcile.store.db import (
    ClusterMemberRow,
    ClusterRow,
    ConstraintRow,
    DecisionRow,
    EventRow,
    MentionRow,
    MetaRow,
    RelationshipRow,
    get_sessionmaker,
    init_db,
)


class DecisionStore:
    def __init__(self, url: str | None = None, create: bool = False):
        if create:
            init_db(url)
        self._Session = get_sessionmaker(url)

    def session(self) -> Session:
        return self._Session()

    # ---- mentions ----------------------------------------------------------
    def upsert_mention(self, m: Mention) -> None:
        with self.session() as s:
            row = s.get(MentionRow, m.id)
            if row is None:
                row = MentionRow(id=m.id)
                s.add(row)
            row.name = m.name
            row.entity_type = m.entity_type
            row.attributes = dict(m.attributes)
            row.source = m.source
            s.commit()

    def get_mentions(self) -> list[Mention]:
        with self.session() as s:
            rows = s.scalars(select(MentionRow)).all()
            return [
                Mention(
                    id=r.id,
                    name=r.name,
                    entity_type=r.entity_type,
                    attributes=dict(r.attributes or {}),
                    source=r.source,
                )
                for r in rows
            ]

    # ---- relationships -----------------------------------------------------
    def add_relationship(self, rel: Relationship) -> None:
        with self.session() as s:
            s.add(RelationshipRow(src=rel.src, dst=rel.dst, edge_type=rel.edge_type))
            s.commit()

    def get_relationships(self) -> list[Relationship]:
        with self.session() as s:
            rows = s.scalars(select(RelationshipRow)).all()
            return [Relationship(src=r.src, dst=r.dst, edge_type=r.edge_type) for r in rows]

    # ---- constraints -------------------------------------------------------
    def add_constraint(self, c: ConstraintRecord) -> None:
        with self.session() as s:
            s.add(
                ConstraintRow(
                    kind=c.kind.value,
                    a=c.a,
                    b=c.b,
                    source=c.source.value,
                    confidence=c.confidence,
                    evidence=dict(c.evidence),
                    active=True,
                    created_at=c.created_at,
                )
            )
            s.commit()

    def get_constraints(self, active_only: bool = True) -> list[ConstraintRecord]:
        with self.session() as s:
            stmt = select(ConstraintRow)
            if active_only:
                stmt = stmt.where(ConstraintRow.active.is_(True))
            rows = s.scalars(stmt.order_by(ConstraintRow.created_at)).all()
            return [
                ConstraintRecord(
                    kind=ConstraintKind(r.kind),
                    a=r.a,
                    b=r.b,
                    source=DecisionSource(r.source),
                    confidence=r.confidence,
                    evidence=dict(r.evidence or {}),
                    created_at=r.created_at,
                )
                for r in rows
            ]

    # ---- decisions / review queue -----------------------------------------
    def record_decision(self, d: PairDecision) -> None:
        with self.session() as s:
            s.add(
                DecisionRow(
                    a=d.a,
                    b=d.b,
                    score=d.score,
                    band=d.band.value,
                    evidence=dict(d.evidence),
                    resolved=False,
                )
            )
            s.commit()

    def get_review_queue(self) -> list[PairDecision]:
        from reconcile.models import Band

        with self.session() as s:
            rows = s.scalars(
                select(DecisionRow)
                .where(DecisionRow.band == Band.REVIEW.value)
                .where(DecisionRow.resolved.is_(False))
                .order_by(DecisionRow.score.desc())
            ).all()
            return [
                PairDecision(
                    a=r.a, b=r.b, score=r.score, band=Band(r.band), evidence=dict(r.evidence or {})
                )
                for r in rows
            ]

    def clear_unresolved_reviews(self) -> None:
        """Drop unresolved REVIEW rows so the queue reflects the latest resolution run."""
        from reconcile.models import Band

        with self.session() as s:
            s.execute(
                delete(DecisionRow)
                .where(DecisionRow.band == Band.REVIEW.value)
                .where(DecisionRow.resolved.is_(False))
            )
            s.commit()

    def mark_review_resolved(self, a: str, b: str) -> None:
        with self.session() as s:
            for r in s.scalars(
                select(DecisionRow).where(DecisionRow.a.in_([a, b])).where(DecisionRow.b.in_([a, b]))
            ).all():
                r.resolved = True
            s.commit()

    # ---- cluster projection (current assignment) ---------------------------
    def save_clusters(self, clusters: list[Cluster]) -> None:
        """Replace the live cluster assignment with the given clusters."""
        with self.session() as s:
            s.execute(delete(ClusterMemberRow))
            # keep retired clusters for lineage, drop only live ones being replaced
            s.execute(delete(ClusterRow).where(ClusterRow.retired.is_(False)))
            for c in clusters:
                s.add(ClusterRow(id=c.cluster_id, attributes=dict(c.attributes), retired=False))
                for mid in sorted(c.members):
                    s.add(ClusterMemberRow(cluster_id=c.cluster_id, mention_id=mid))
            s.commit()

    def get_clusters(self) -> list[Cluster]:
        with self.session() as s:
            rows = s.scalars(
                select(ClusterRow).where(ClusterRow.retired.is_(False))
            ).all()
            out = []
            for r in rows:
                members = {m.mention_id for m in r.members}
                out.append(Cluster(cluster_id=r.id, members=members, attributes=dict(r.attributes or {})))
            return out

    # ---- change events -----------------------------------------------------
    def add_event(self, e: ChangeEvent) -> None:
        with self.session() as s:
            s.add(
                EventRow(
                    kind=e.kind.value,
                    old_ids=list(e.old_ids),
                    new_ids=list(e.new_ids),
                    detail=dict(e.detail),
                    created_at=e.created_at,
                )
            )
            s.commit()

    def get_events(self) -> list[ChangeEvent]:
        from reconcile.models import EventKind

        with self.session() as s:
            rows = s.scalars(select(EventRow).order_by(EventRow.created_at)).all()
            return [
                ChangeEvent(
                    kind=EventKind(r.kind),
                    old_ids=list(r.old_ids or []),
                    new_ids=list(r.new_ids or []),
                    detail=dict(r.detail or {}),
                    created_at=r.created_at,
                )
                for r in rows
            ]

    # ---- stable id minting -------------------------------------------------
    def mint_cluster_id(self) -> str:
        with self.session() as s:
            row = s.get(MetaRow, "cluster_seq")
            if row is None:
                row = MetaRow(key="cluster_seq", value="0")
                s.add(row)
            n = int(row.value) + 1
            row.value = str(n)
            s.commit()
            return f"c-{n:04d}"
