"""SQLAlchemy ORM schema + engine/session factory for the decision store.

The decision store is the source of truth for identity. It persists everything
needed to re-cluster from scratch (mentions, relationships, constraints) plus the
current cluster projection and the change-event log. Postgres in prod; SQLite for
offline eval/tests via the default DATABASE_URL.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    String,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from reconcile.config import get_settings


class Base(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


class MentionRow(Base):
    __tablename__ = "mentions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    entity_type: Mapped[str] = mapped_column(String, default="Entity")
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    source: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class RelationshipRow(Base):
    __tablename__ = "relationships"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    src: Mapped[str] = mapped_column(String, nullable=False)
    dst: Mapped[str] = mapped_column(String, nullable=False)
    edge_type: Mapped[str] = mapped_column(String, default="RELATES_TO")


class ConstraintRow(Base):
    __tablename__ = "constraints"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String, nullable=False)  # must_link | cannot_link
    a: Mapped[str] = mapped_column(String, nullable=False)
    b: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, default="machine")  # machine | human
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class DecisionRow(Base):
    __tablename__ = "decisions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    a: Mapped[str] = mapped_column(String, nullable=False)
    b: Mapped[str] = mapped_column(String, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    band: Mapped[str] = mapped_column(String, nullable=False)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    resolved: Mapped[bool] = mapped_column(default=False)  # human acted on a REVIEW row
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ClusterRow(Base):
    __tablename__ = "clusters"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    retired: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    members: Mapped[list[ClusterMemberRow]] = relationship(
        back_populates="cluster", cascade="all, delete-orphan"
    )


class ClusterMemberRow(Base):
    __tablename__ = "cluster_members"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cluster_id: Mapped[str] = mapped_column(ForeignKey("clusters.id", ondelete="CASCADE"))
    mention_id: Mapped[str] = mapped_column(String, nullable=False)

    cluster: Mapped[ClusterRow] = relationship(back_populates="members")


class EventRow(Base):
    __tablename__ = "change_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    old_ids: Mapped[list] = mapped_column(JSON, default=list)
    new_ids: Mapped[list] = mapped_column(JSON, default=list)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class MetaRow(Base):
    __tablename__ = "meta"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String, default="")


class EmbeddingRow(Base):
    """Persistent embedding cache: sha256(model_id + text) -> JSON vector."""

    __tablename__ = "embeddings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    vector: Mapped[list] = mapped_column(JSON, default=list)


_engine = None
_Session = None


def get_engine(url: str | None = None):
    global _engine
    if url is not None:
        return create_engine(url, future=True)
    if _engine is None:
        _engine = create_engine(get_settings().database_url, future=True)
    return _engine


def get_sessionmaker(url: str | None = None):
    global _Session
    if url is not None:
        return sessionmaker(bind=get_engine(url), future=True)
    if _Session is None:
        _Session = sessionmaker(bind=get_engine(), future=True)
    return _Session


def init_db(url: str | None = None) -> None:
    """Create all tables. Used for SQLite/tests; prod uses Alembic migrations."""
    Base.metadata.create_all(get_engine(url))
