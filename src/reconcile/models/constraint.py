"""Constraints are the durable, source-of-truth record of identity decisions.

A must_link says "these two mentions are the same entity"; a cannot_link says
"these two mentions are NOT the same entity". Human constraints outrank machine
constraints and are what make a split survive re-ingestion (constraint replay).
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ConstraintKind(StrEnum):
    MUST_LINK = "must_link"
    CANNOT_LINK = "cannot_link"


class DecisionSource(StrEnum):
    MACHINE = "machine"
    HUMAN = "human"


def _now() -> datetime:
    return datetime.now(UTC)


class ConstraintRecord(BaseModel):
    kind: ConstraintKind
    a: str  # mention id
    b: str  # mention id
    source: DecisionSource = DecisionSource.MACHINE
    confidence: float = 1.0
    evidence: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)

    @property
    def pair(self) -> tuple[str, str]:
        return tuple(sorted((self.a, self.b)))  # type: ignore[return-value]
