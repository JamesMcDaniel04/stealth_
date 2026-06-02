"""In-memory GraphStore. Lets the wedge run end-to-end with zero external services."""

from __future__ import annotations

from reconcile.models import Cluster, Mention, Relationship


class StubGraphStore:
    def __init__(self) -> None:
        self._entities: dict[str, Mention] = {}
        self._rels: list[Relationship] = []
        self._projection: dict[str, set[str]] = {}
        self._resolved_edges: set[tuple[str, str, str]] = set()

    def upsert_entities(self, mentions: list[Mention]) -> None:
        for m in mentions:
            self._entities[m.id] = m

    def upsert_relationships(self, relationships: list[Relationship]) -> None:
        existing = {(r.src, r.dst, r.edge_type) for r in self._rels}
        for r in relationships:
            if (r.src, r.dst, r.edge_type) not in existing:
                self._rels.append(r)
                existing.add((r.src, r.dst, r.edge_type))

    def read_entities(self) -> list[Mention]:
        return list(self._entities.values())

    def read_relationships(self) -> list[Relationship]:
        return list(self._rels)

    def project(
        self, clusters: list[Cluster], resolved_edges: set[tuple[str, str, str]]
    ) -> None:
        self._projection = {c.cluster_id: set(c.members) for c in clusters}
        self._resolved_edges = set(resolved_edges)

    def read_projection(self) -> dict[str, set[str]]:
        return {k: set(v) for k, v in self._projection.items()}

    def resolved_relationships(self) -> set[tuple[str, str, str]]:
        return set(self._resolved_edges)

    def clear(self) -> None:
        self._entities.clear()
        self._rels.clear()
        self._projection.clear()
        self._resolved_edges.clear()

    def close(self) -> None:  # nothing to close
        pass
