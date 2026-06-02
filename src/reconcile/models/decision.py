"""Per-pair scoring decisions, confidence bands, and identity change events."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class Band(StrEnum):
    AUTO_MERGE = "auto_merge"
    REVIEW = "review"
    AUTO_REJECT = "auto_reject"


class PairDecision(BaseModel):
    a: str
    b: str
    score: float
    band: Band
    # Per-feature contribution breakdown — drives the future review-queue explanation.
    evidence: dict[str, float] = Field(default_factory=dict)

    @property
    def pair(self) -> tuple[str, str]:
        return tuple(sorted((self.a, self.b)))  # type: ignore[return-value]


class EventKind(StrEnum):
    MERGE = "merge"
    SPLIT = "split"


def _now() -> datetime:
    return datetime.now(UTC)


class ChangeEvent(BaseModel):
    """Emitted so downstream consumers learn that stable IDs merged or split."""

    kind: EventKind
    # For SPLIT: old_ids == [original], new_ids == [resulting...].
    # For MERGE: old_ids == [merged...], new_ids == [survivor].
    old_ids: list[str]
    new_ids: list[str]
    detail: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)
