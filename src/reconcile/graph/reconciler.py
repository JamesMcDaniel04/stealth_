"""Reconciler — projects decision-store clusters onto the graph.

The graph is a projection of resolution decisions, so projection is idempotent:
call it after any merge, split, or replay and the resolved layer reconciles to the
current cluster state. It never mutates source :Entity nodes.
"""

from __future__ import annotations

from reconcile.graph.base import GraphStore, resolved_edges_for
from reconcile.models import Cluster, Relationship


class Reconciler:
    def __init__(self, store: GraphStore):
        self.store = store

    def project(self, clusters: list[Cluster], relationships: list[Relationship]) -> None:
        edges = resolved_edges_for(clusters, relationships)
        self.store.project(clusters, edges)
