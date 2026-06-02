"""Request/response models for the API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class MentionIn(BaseModel):
    id: str
    name: str
    type: str = "Entity"
    attributes: dict[str, str] = Field(default_factory=dict)
    source: str = ""


class RelationshipIn(BaseModel):
    src: str
    dst: str
    type: str = "RELATES_TO"


class IngestRequest(BaseModel):
    mentions: list[MentionIn] = Field(default_factory=list)
    relationships: list[RelationshipIn] = Field(default_factory=list)


class DecisionRequest(BaseModel):
    a: str
    b: str
    same: bool
    evidence: dict = Field(default_factory=dict)


class SplitRequest(BaseModel):
    a: str
    b: str
    evidence: dict = Field(default_factory=dict)


class ClusterOut(BaseModel):
    cluster_id: str
    members: list[str]


class EventOut(BaseModel):
    kind: str
    old_ids: list[str]
    new_ids: list[str]


class ResolveResponse(BaseModel):
    clusters: list[ClusterOut]
    events: list[EventOut]


class ReviewItem(BaseModel):
    a: str
    b: str
    score: float
    evidence: dict[str, float]
