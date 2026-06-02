"""The defining demo — the screen-recordable artifact.

Three acts:
  1. KEEP-SEPARATE  — collective resolution keeps "Acme Inc" and "Acme Corp" apart
                      where an embedding-only baseline would merge them.
  2. REVERSIBLE SPLIT — a naive system force-merges them; contradicting evidence
                      arrives; a reviewer splits the node back into two.
  3. PERSISTENCE     — a new extraction re-mentions Acme; the split SURVIVES via
                      constraint replay, with zero manual re-fixing.

Runs against live Neo4j when reachable (the resolved layer is written there), and
falls back to an in-memory graph otherwise. The decision store is a fresh SQLite db
so the run is fully reproducible; Postgres is used in production (see .env.example).
"""

from __future__ import annotations

import os
from pathlib import Path

from reconcile.dataset import load_episode
from reconcile.embeddings import make_embedder
from reconcile.graph import StubGraphStore
from reconcile.models import DecisionSource
from reconcile.ops import Engine
from reconcile.resolution.features import FeatureContext
from reconcile.resolution.scorer import embedding_only_prob
from reconcile.store import DecisionStore

DATASET = Path(__file__).parent / "dataset.yaml"
DEMO_DB = Path(__file__).parent / "_demo.db"


def _rule(title: str) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def _show_graph(engine: Engine) -> None:
    proj = engine.graph.read_projection()
    print(f"  resolved entities in graph: {len(proj)}")
    for cid in sorted(proj):
        print(f"    {cid}: {sorted(proj[cid])}")


def _make_graph_store():
    if os.environ.get("RECONCILE_FORCE_STUB"):
        return StubGraphStore(), "in-memory (forced)"
    try:
        from reconcile.graph.neo4j_store import Neo4jStore

        store = Neo4jStore()
        store.clear()
        return store, "Neo4j (live)"
    except Exception as exc:  # noqa: BLE001 — demo should degrade, not crash
        return StubGraphStore(), f"in-memory (Neo4j unavailable: {type(exc).__name__})"


def main() -> int:
    DEMO_DB.unlink(missing_ok=True)
    store = DecisionStore(url=f"sqlite:///{DEMO_DB}", create=True)
    graph, graph_kind = _make_graph_store()
    embedder = make_embedder()
    engine = Engine(store=store, graph=graph, embedder=embedder)
    print(f"graph store: {graph_kind}   embedder: {embedder.model_id}")

    m1, r1 = load_episode(DATASET, "episode_1")

    # ---- ACT 1 ----------------------------------------------------------
    _rule("ACT 1 — collective resolution keeps look-alikes apart")
    engine.ingest(m1, r1)

    ctx = FeatureContext.build(m1, r1, embedder=embedder)
    f = ctx.features("acme-inc", "acme-corp")
    emb = embedding_only_prob(f.embedding_cosine)
    print("  'Acme Inc' vs 'Acme Corp':")
    print(f"    name similarity        : {f.name_sim:.2f}  (looks like the same company)")
    print(f"    embedding-only p(same) : {emb:.2f}  -> a string/embedding deduper MERGES them")
    print(f"    anchor conflict        : {f.anchor_conflict:.0f}    (diff domain + Salesforce id)")
    print(f"    shared neighbors       : {f.raw_shared_neighbors}    (disjoint relationships)")

    engine.resolve()
    separate = not engine.same_cluster("acme-inc", "acme-corp")
    print(f"\n  collective resolution keeps them SEPARATE: {separate}")
    _show_graph(engine)
    assert separate, "collective resolution should keep Acme Inc and Acme Corp apart"

    # ---- ACT 2 ----------------------------------------------------------
    _rule("ACT 2 — a wrong merge, then a reversible split")
    print("  A naive pipeline force-merges them on the shared name...")
    engine.submit_decision("acme-inc", "acme-corp", same=True, source=DecisionSource.MACHINE)
    merged = engine.same_cluster("acme-inc", "acme-corp")
    print(f"  merged into one node: {merged}")
    _show_graph(engine)

    print("\n  Contradicting evidence surfaces (conflicting Salesforce ids); a reviewer splits:")
    result = engine.split(
        "acme-inc", "acme-corp",
        source=DecisionSource.HUMAN,
        evidence={"reason": "SF-001 vs SF-002 are distinct accounts"},
    )
    split_ok = not engine.same_cluster("acme-inc", "acme-corp")
    print(f"  split back into two nodes: {split_ok}")
    for e in result.events:
        print(f"    change event: {e.kind.value}  {e.old_ids} -> {e.new_ids}")
    _show_graph(engine)
    assert split_ok, "the split should separate them again"

    # ---- ACT 3 ----------------------------------------------------------
    _rule("ACT 3 — the split persists through re-ingestion (the moat)")
    m2, r2 = load_episode(DATASET, "episode_2")
    print("  New extraction arrives: a fresh 'Acme' mention (same domain + Salesforce id).")
    engine.ingest(m2, r2)
    engine.resolve()  # replays the human cannot-link before writing

    still_separate = not engine.same_cluster("acme-inc", "acme-corp")
    new_merged_into_inc = engine.same_cluster("acme-inc", "acme-inc-2")
    print(f"  new 'Acme' merged into Acme Inc      : {new_merged_into_inc}")
    print(f"  Acme Inc / Acme Corp STILL separate  : {still_separate}  (no manual re-fixing)")
    _show_graph(engine)

    engine.graph.close()
    assert still_separate, "MOAT: human split must survive re-ingestion"
    assert new_merged_into_inc, "the new mention should still resolve to Acme Inc"

    _rule("DEMO PASSED — collective + reversible + persistent")
    print("  Acme Inc and Acme Corp: kept apart, force-merged, split back, and the")
    print("  split held through a new extraction. That is the wedge.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
