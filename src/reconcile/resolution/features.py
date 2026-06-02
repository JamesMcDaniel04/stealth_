"""Relational + string + anchor features for a candidate mention pair.

This is the heart of *collective* resolution: most features describe the two
mentions' relationship neighborhoods, not their strings. A `neighbor_map` lets the
collective step remap neighbors to their current cluster representative, so merges
made earlier in a propagation round become shared neighbors in the next round.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from reconcile.embeddings import Embedder, cosine, default_embedder
from reconcile.models import Mention, Relationship

# Anchor attribute keys in priority order. The first key present in *both* mentions
# decides anchor agreement/conflict (an authoritative external_id beats a domain).
ANCHOR_KEYS = ("external_id", "email", "domain")


@dataclass
class PairFeatures:
    name_sim: float
    embedding_cosine: float
    jaccard_neighbors: float
    # Adamic-Adar: shared neighbors weighted by how discriminative each is
    # (1/log of the neighbor's degree). Sharing a CFO counts; sharing an employer
    # — a high-degree hub — barely does. This is what stops two co-workers from
    # being merged just because they share an employer.
    adamic_adar: float
    edge_type_overlap: float
    anchor_agreement: float
    anchor_conflict: float
    raw_shared_neighbors: int = 0

    def as_dict(self) -> dict[str, float]:
        return {
            "name_sim": self.name_sim,
            "embedding_cosine": self.embedding_cosine,
            "jaccard_neighbors": self.jaccard_neighbors,
            "adamic_adar": self.adamic_adar,
            "edge_type_overlap": self.edge_type_overlap,
            "anchor_agreement": self.anchor_agreement,
            "anchor_conflict": self.anchor_conflict,
        }


@dataclass
class FeatureContext:
    """Holds the mention set + relationship graph and computes pair features."""

    mentions: dict[str, Mention]
    # undirected neighbor ids per mention
    neighbors: dict[str, set[str]] = field(default_factory=dict)
    # edge types incident to a mention
    edge_types: dict[str, set[str]] = field(default_factory=dict)
    embedder: Embedder = field(default_factory=default_embedder)
    _emb_cache: dict[str, object] = field(default_factory=dict)
    _deg_cache: dict[int, dict[str, int]] = field(default_factory=dict)

    @classmethod
    def build(
        cls,
        mentions: list[Mention],
        relationships: list[Relationship],
        embedder: Embedder | None = None,
    ) -> FeatureContext:
        ctx = cls(
            mentions={m.id: m for m in mentions},
            embedder=embedder or default_embedder(),
        )
        for m in mentions:
            ctx.neighbors.setdefault(m.id, set())
            ctx.edge_types.setdefault(m.id, set())
        for r in relationships:
            ctx.neighbors.setdefault(r.src, set()).add(r.dst)
            ctx.neighbors.setdefault(r.dst, set()).add(r.src)
            ctx.edge_types.setdefault(r.src, set()).add(r.edge_type)
            ctx.edge_types.setdefault(r.dst, set()).add(r.edge_type)
        return ctx

    def _emb(self, mid: str):
        if mid not in self._emb_cache:
            self._emb_cache[mid] = self.embedder.embed(self.mentions[mid].name)
        return self._emb_cache[mid]

    def _mapped_neighbors(self, mid: str, neighbor_map: dict[str, str] | None) -> set[str]:
        ns = self.neighbors.get(mid, set())
        if not neighbor_map:
            return set(ns)
        return {neighbor_map.get(n, n) for n in ns}

    def _mapped_degree(self, neighbor_map: dict[str, str] | None) -> dict[str, int]:
        """Degree of every node in the cluster-mapped graph (cached per map identity)."""
        key = id(neighbor_map) if neighbor_map else 0
        cached = self._deg_cache.get(key)
        if cached is not None:
            return cached
        adj: dict[str, set[str]] = {}
        for mid, ns in self.neighbors.items():
            rm = neighbor_map.get(mid, mid) if neighbor_map else mid
            for n in ns:
                rn = neighbor_map.get(n, n) if neighbor_map else n
                if rn != rm:
                    adj.setdefault(rm, set()).add(rn)
        deg = {k: len(v) for k, v in adj.items()}
        self._deg_cache[key] = deg
        return deg

    def _anchor_signal(self, a: Mention, b: Mention) -> tuple[float, float]:
        for key in ANCHOR_KEYS:
            va, vb = a.anchor(key), b.anchor(key)
            if va is not None and vb is not None:
                return (1.0, 0.0) if va == vb else (0.0, 1.0)
        return (0.0, 0.0)

    def features(
        self, a_id: str, b_id: str, neighbor_map: dict[str, str] | None = None
    ) -> PairFeatures:
        a, b = self.mentions[a_id], self.mentions[b_id]

        name_sim = fuzz.token_set_ratio(a.name, b.name) / 100.0

        emb_cos = cosine(self._emb(a_id), self._emb(b_id))

        na = self._mapped_neighbors(a_id, neighbor_map) - {a_id, b_id}
        nb = self._mapped_neighbors(b_id, neighbor_map) - {a_id, b_id}
        # don't let the two mentions' own (possibly merged) ids count as shared
        if neighbor_map:
            na.discard(neighbor_map.get(b_id, b_id))
            nb.discard(neighbor_map.get(a_id, a_id))
        inter = na & nb
        union = na | nb
        jaccard = len(inter) / len(union) if union else 0.0

        deg = self._mapped_degree(neighbor_map)
        adamic_adar = sum(1.0 / math.log2(2.0 + deg.get(n, 1)) for n in inter)

        ea, eb = self.edge_types.get(a_id, set()), self.edge_types.get(b_id, set())
        eunion = ea | eb
        edge_overlap = len(ea & eb) / len(eunion) if eunion else 0.0

        agreement, conflict = self._anchor_signal(a, b)

        return PairFeatures(
            name_sim=name_sim,
            embedding_cosine=emb_cos,
            jaccard_neighbors=jaccard,
            adamic_adar=adamic_adar,
            edge_type_overlap=edge_overlap,
            anchor_agreement=agreement,
            anchor_conflict=conflict,
            raw_shared_neighbors=len(inter),
        )
