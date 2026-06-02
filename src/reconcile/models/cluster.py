"""A Cluster is a stable identity: a set of mention ids under one stable cluster_id.

This is the "living cluster" pattern. Merges and splits are operations on cluster
membership; the stable id is what the graph projection keys off of.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Cluster(BaseModel):
    cluster_id: str
    members: set[str] = Field(default_factory=set)
    attributes: dict[str, str] = Field(default_factory=dict)

    def with_members(self, members: set[str]) -> "Cluster":
        return Cluster(cluster_id=self.cluster_id, members=set(members), attributes=self.attributes)
