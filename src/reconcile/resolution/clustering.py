"""Constrained clustering — union-find that honors must-link and cannot-link.

This is where constraint replay lives: cannot-link constraints are registered
*first* as forbidden partnerships, then human must-links, then machine merges (by
descending confidence). A machine merge that would re-join a human-split pair is
silently refused. That ordering is the whole reason a split survives re-ingestion.
"""

from __future__ import annotations

from reconcile.models import Cluster, ConstraintKind, ConstraintRecord


class ConstrainedClusterer:
    def __init__(self, members: list[str]):
        self._parent: dict[str, str] = {m: m for m in members}
        self._members: dict[str, set[str]] = {m: {m} for m in members}
        # forbidden[root] = mention ids that may never share a cluster with this root
        self._forbidden: dict[str, set[str]] = {m: set() for m in members}

    def _ensure(self, x: str) -> None:
        if x not in self._parent:
            self._parent[x] = x
            self._members[x] = {x}
            self._forbidden[x] = set()

    def find(self, x: str) -> str:
        self._ensure(x)
        root = x
        while self._parent[root] != root:
            root = self._parent[root]
        # path compression
        while self._parent[x] != root:
            self._parent[x], x = root, self._parent[x]
        return root

    def cannot_link(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        # forbid the two *clusters* from ever merging
        self._forbidden[ra] |= self._members[rb]
        self._forbidden[rb] |= self._members[ra]

    def would_violate(self, a: str, b: str) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        return bool(self._members[rb] & self._forbidden[ra]) or bool(
            self._members[ra] & self._forbidden[rb]
        )

    def union(self, a: str, b: str) -> bool:
        """Merge a,b unless forbidden. Returns True if merged."""
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return True
        if self.would_violate(a, b):
            return False
        # attach smaller under larger
        if len(self._members[ra]) < len(self._members[rb]):
            ra, rb = rb, ra
        self._parent[rb] = ra
        self._members[ra] |= self._members[rb]
        self._forbidden[ra] |= self._forbidden[rb]
        del self._members[rb]
        del self._forbidden[rb]
        return True

    def groups(self) -> list[set[str]]:
        out: dict[str, set[str]] = {}
        for m in list(self._parent):
            out.setdefault(self.find(m), set()).add(m)
        return list(out.values())


def clusters_from(
    members: list[str],
    merges: list[tuple[str, str, float]],
    constraints: list[ConstraintRecord] | None = None,
) -> list[set[str]]:
    """Cluster `members` given scored machine `merges` and persisted `constraints`.

    Order is load-bearing:
      1. cannot-link constraints  -> register forbidden partnerships
      2. must-link constraints    -> forced unions (respect forbiddens)
      3. machine merges           -> by descending confidence (respect forbiddens)
    """
    clusterer = ConstrainedClusterer(members)
    constraints = constraints or []

    for c in constraints:
        if c.kind is ConstraintKind.CANNOT_LINK:
            clusterer.cannot_link(c.a, c.b)
    for c in constraints:
        if c.kind is ConstraintKind.MUST_LINK:
            clusterer.union(c.a, c.b)
    for a, b, _conf in sorted(merges, key=lambda t: t[2], reverse=True):
        clusterer.union(a, b)

    return clusterer.groups()


def to_clusters(groups: list[set[str]], ids: list[str]) -> list[Cluster]:
    out = []
    for grp, cid in zip(groups, ids, strict=True):
        out.append(Cluster(cluster_id=cid, members=set(grp)))
    return out
