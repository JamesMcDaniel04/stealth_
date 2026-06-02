"""GraphStore protocol + the resolved-edge projection helper.

A GraphStore is where extracted entities land (input) and where the resolved
identity layer is projected (output). The projection is *non-destructive*: we never
mutate the source :Entity nodes; we add a :ResolvedEntity layer linked by
:RESOLVES_TO. Merge/split is just rewiring that layer.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from reconcile.models import Cluster, Mention, Relationship


@runtime_checkable
class GraphStore(Protocol):
    # --- input: candidate entities (e.g. from Graphiti extraction) ---
    def upsert_entities(self, mentions: list[Mention]) -> None: ...
    def upsert_relationships(self, relationships: list[Relationship]) -> None: ...
    def read_entities(self) -> list[Mention]: ...
    def read_relationships(self) -> list[Relationship]: ...

    # --- output: the resolved identity projection ---
    def project(
        self, clusters: list[Cluster], resolved_edges: set[tuple[str, str, str]]
    ) -> None: ...
    def read_projection(self) -> dict[str, set[str]]: ...  # cluster_id -> mention ids
    def resolved_relationships(self) -> set[tuple[str, str, str]]: ...

    def clear(self) -> None: ...
    def close(self) -> None: ...


def resolved_edges_for(
    clusters: list[Cluster], relationships: list[Relationship]
) -> set[tuple[str, str, str]]:
    """Lift mention-level relationships to cluster-level resolved edges.

    A relationship (m_a)-[T]->(m_b) becomes (cluster_of_a)-[T]->(cluster_of_b).
    Self-edges (both mentions in one cluster) are dropped.
    """
    owner: dict[str, str] = {}
    for c in clusters:
        for mid in c.members:
            owner[mid] = c.cluster_id
    edges: set[tuple[str, str, str]] = set()
    for r in relationships:
        ca, cb = owner.get(r.src), owner.get(r.dst)
        if ca is None or cb is None or ca == cb:
            continue
        edges.add((ca, r.edge_type, cb))
    return edges
