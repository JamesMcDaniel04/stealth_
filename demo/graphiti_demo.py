"""Live free-text → Claude extraction → resolution → Neo4j projection.

Reads two CRM call-notes that mention the same company two different ways, runs them
through Graphiti (LLM = Claude), resolves with the relational scorer, and projects the
resolved identity layer into Neo4j. Needs ANTHROPIC_API_KEY + OPENAI_API_KEY + Neo4j;
prints setup instructions and exits cleanly if anything is missing.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from reconcile.config import get_settings
from reconcile.ops import Engine
from reconcile.store import DecisionStore

DEMO_DB = Path(__file__).parent / "_graphiti_demo.db"

EPISODES = [
    ("call-notes-jan", "Had a discovery call with Acme Corporation. Their CFO Jane Doe joined. "
                       "Acme Corporation is a Boston-based manufacturer."),
    ("call-notes-feb", "Follow-up with Acme today — Jane Doe presented the rollout plan. "
                       "Acme is opening a European office."),
]


async def main() -> int:
    s = get_settings()
    if not (s.anthropic_api_key and s.openai_api_key):
        print("This demo needs ANTHROPIC_API_KEY (Claude extraction) and OPENAI_API_KEY "
              "(embeddings) in .env, plus `make up` for Neo4j.")
        print("The offline wedge demo (no keys) is: make demo")
        return 0

    try:
        from reconcile.graph.graphiti_ingest import GraphitiIngest
        from reconcile.graph.neo4j_store import Neo4jStore
    except Exception as exc:  # noqa: BLE001
        print(f"Graphiti/Neo4j unavailable: {exc}")
        return 0

    DEMO_DB.unlink(missing_ok=True)
    store = DecisionStore(url=f"sqlite:///{DEMO_DB}", create=True)
    graph = Neo4jStore()
    graph.clear()
    engine = Engine(store=store, graph=graph)

    ingest = GraphitiIngest()
    print("Extracting entities from free text via Claude...")
    try:
        await ingest.setup()
        for name, text in EPISODES:
            mentions, rels = await ingest.extract(name, text, group_id=name)
            print(f"  {name}: {len(mentions)} entities, {len(rels)} relationships")
            engine.ingest(mentions, rels)
    finally:
        await ingest.close()

    result = engine.resolve()
    print(f"\nResolved into {len(result.clusters)} entities:")
    for c in sorted(result.clusters, key=lambda c: c.cluster_id):
        names = [m.name for m in store.get_mentions() if m.id in c.members]
        print(f"  {c.cluster_id}: {names}")
    print("\nThe resolved layer is now in Neo4j (:ResolvedEntity / :RESOLVES_TO).")
    graph.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
