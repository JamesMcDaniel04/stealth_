"""Engine — the public orchestration surface for the resolution lifecycle.

One object ties together: ingest -> resolve (with constraint replay) -> project,
plus reversible split and human review decisions. The decision store is the source
of truth; the graph is reprojected from it after every operation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from reconcile.config import get_settings
from reconcile.embeddings import CachedEmbedder, Embedder, make_embedder
from reconcile.graph.base import GraphStore
from reconcile.graph.reconciler import Reconciler
from reconcile.models import (
    Band,
    ChangeEvent,
    Cluster,
    ConstraintKind,
    ConstraintRecord,
    DecisionSource,
    Mention,
    PairDecision,
    Relationship,
)
from reconcile.ops.events import diff_events
from reconcile.ops.replay import load_constraints
from reconcile.resolution.bander import band_decisions, band_for_score
from reconcile.resolution.collective import CollectiveResolver
from reconcile.resolution.features import FeatureContext
from reconcile.resolution.scorer import WeightedRuleScorer
from reconcile.store import DecisionStore


@dataclass
class ResolveResult:
    clusters: list[Cluster]
    decisions: list[PairDecision]
    events: list[ChangeEvent] = field(default_factory=list)


class Engine:
    def __init__(
        self,
        store: DecisionStore,
        graph: GraphStore,
        embedder: Embedder | None = None,
        merge_threshold: float = 0.55,
    ):
        self.store = store
        self.graph = graph
        # Default: real embedder when a key is configured (else stub), behind a
        # persistent cache so each distinct name is embedded once. Tests inject a stub.
        self.embedder = embedder or CachedEmbedder(make_embedder(), store)
        self.scorer = WeightedRuleScorer()
        self.merge_threshold = merge_threshold
        self.reconciler = Reconciler(graph)
        s = get_settings()
        self.auto_merge = s.reconcile_auto_merge_threshold
        self.auto_reject = s.reconcile_auto_reject_threshold

    # ---- ingest ------------------------------------------------------------
    def ingest(self, mentions: list[Mention], relationships: list[Relationship]) -> None:
        """Persist candidate entities to the source of truth and the graph input layer."""
        for m in mentions:
            self.store.upsert_mention(m)
        for r in relationships:
            self.store.add_relationship(r)
        self.graph.upsert_entities(mentions)
        self.graph.upsert_relationships(relationships)

    # ---- resolve (with replay) --------------------------------------------
    def resolve(self) -> ResolveResult:
        mentions = self.store.get_mentions()
        relationships = self.store.get_relationships()
        constraints = load_constraints(self.store)  # <- replay: applied before any write

        ctx = FeatureContext.build(mentions, relationships, embedder=self.embedder)
        result = CollectiveResolver(ctx, self.scorer, self.merge_threshold).resolve(constraints)

        prev = self.store.get_clusters()
        new_clusters = self._assign_stable_ids(result.clusters, prev)
        events = diff_events(prev, new_clusters)

        self.store.save_clusters(new_clusters)
        for e in events:
            self.store.add_event(e)

        decisions = self._record_review_queue(result)
        self.reconciler.project(new_clusters, relationships)

        return ResolveResult(clusters=new_clusters, decisions=decisions, events=events)

    # ---- reversible split --------------------------------------------------
    def split(
        self,
        a: str,
        b: str,
        source: DecisionSource = DecisionSource.HUMAN,
        evidence: dict | None = None,
    ) -> ResolveResult:
        """Declare a and b distinct (cannot-link) and re-project. Reversible & durable."""
        return self._decide(a, b, ConstraintKind.CANNOT_LINK, source, evidence)

    def retract(self, a: str, b: str) -> ResolveResult:
        """Undo: deactivate any constraint on {a,b} and re-resolve.

        A retracted split lets the pair re-merge if the scorer now wants to; a
        retracted merge lets it re-separate. True two-way reversibility.
        """
        self.store.deactivate_constraints(a, b)
        return self.resolve()

    # human-readable alias for retracting a split specifically
    def undo_split(self, a: str, b: str) -> ResolveResult:
        return self.retract(a, b)

    # ---- human review decision --------------------------------------------
    def submit_decision(
        self,
        a: str,
        b: str,
        same: bool,
        source: DecisionSource = DecisionSource.HUMAN,
        evidence: dict | None = None,
    ) -> ResolveResult:
        kind = ConstraintKind.MUST_LINK if same else ConstraintKind.CANNOT_LINK
        return self._decide(a, b, kind, source, evidence)

    def _decide(
        self,
        a: str,
        b: str,
        kind: ConstraintKind,
        source: DecisionSource,
        evidence: dict | None,
    ) -> ResolveResult:
        """Record a constraint, enforcing latest-human-decision-wins, then re-resolve."""
        # The newest human decision supersedes any prior constraint on the pair, so a
        # must/cannot flip is well-defined and never deadlocks.
        if source is DecisionSource.HUMAN:
            self.store.deactivate_constraints(a, b)
        self.store.add_constraint(
            ConstraintRecord(kind=kind, a=a, b=b, source=source, confidence=1.0,
                             evidence=evidence or {})
        )
        self.store.mark_review_resolved(a, b)
        return self.resolve()

    # ---- queries -----------------------------------------------------------
    def clusters(self) -> list[Cluster]:
        return self.store.get_clusters()

    def cluster_id_of(self, mention_id: str) -> str | None:
        for c in self.store.get_clusters():
            if mention_id in c.members:
                return c.cluster_id
        return None

    def same_cluster(self, a: str, b: str) -> bool:
        ca = self.cluster_id_of(a)
        return ca is not None and ca == self.cluster_id_of(b)

    def review_queue(self) -> list[PairDecision]:
        return self.store.get_review_queue()

    # ---- internals ---------------------------------------------------------
    def _assign_stable_ids(
        self, groups: list[set[str]], prev: list[Cluster]
    ) -> list[Cluster]:
        """Reuse the existing stable id of whichever prior cluster a group most overlaps.

        Each prior id is claimed at most once (by its best-overlapping group); groups
        with no prior overlap mint a fresh id. This keeps the survivor of a split on the
        original id and gives spun-off clusters new ones.
        """
        prev_members = {c.cluster_id: c.members for c in prev}
        candidates: list[tuple[int, int, str]] = []
        for i, g in enumerate(groups):
            for cid, members in prev_members.items():
                overlap = len(g & members)
                if overlap > 0:
                    candidates.append((overlap, i, cid))
        candidates.sort(reverse=True)

        assigned: dict[int, str] = {}
        used: set[str] = set()
        for _overlap, i, cid in candidates:
            if i in assigned or cid in used:
                continue
            assigned[i] = cid
            used.add(cid)

        out: list[Cluster] = []
        for i, g in enumerate(groups):
            cid = assigned.get(i) or self.store.mint_cluster_id()
            out.append(Cluster(cluster_id=cid, members=set(g)))
        return out

    def _record_review_queue(self, result) -> list[PairDecision]:
        decisions = band_decisions(
            result.collective_scores,
            self.auto_merge,
            self.auto_reject,
            contributions=result.contributions,
        )
        self.store.clear_unresolved_reviews()
        for d in decisions:
            if d.band is Band.REVIEW:
                self.store.record_decision(d)
        return decisions

    @staticmethod
    def _band(score: float, auto_merge: float, auto_reject: float) -> Band:
        return band_for_score(score, auto_merge, auto_reject)
