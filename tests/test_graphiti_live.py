"""Live Graphiti extraction via Claude. Requires ANTHROPIC_API_KEY + OPENAI_API_KEY
and a running Neo4j. Run: pytest -m integration. Skipped automatically without keys.

Extraction is non-deterministic, so assertions are deliberately loose (smoke level):
it proves the live pipeline runs end-to-end and produces a resolved graph.
"""

from __future__ import annotations

import uuid

import pytest

from reconcile.config import get_settings
from reconcile.ops import Engine
from reconcile.store import DecisionStore

pytestmark = pytest.mark.integration

EPISODE_1 = (
    "Acme Corporation is a manufacturing company based in Boston. "
    "Jane Doe is the CFO of Acme Corporation."
)
EPISODE_2 = (
    "We had a great call with Acme today. Jane Doe walked us through their roadmap. "
    "Acme is expanding into Europe next year."
)


@pytest.fixture
def keys_present():
    s = get_settings()
    if not (s.anthropic_api_key and s.openai_api_key):
        pytest.skip("ANTHROPIC_API_KEY + OPENAI_API_KEY required for live Graphiti test")


async def test_live_extraction_resolves(tmp_path, keys_present):
    from reconcile.graph.graphiti_ingest import GraphitiIngest
    from reconcile.graph.neo4j_store import Neo4jStore

    graph = Neo4jStore()
    graph.clear()
    store = DecisionStore(url=f"sqlite:///{tmp_path / (uuid.uuid4().hex + '.db')}", create=True)
    engine = Engine(store=store, graph=graph)

    ingest = GraphitiIngest()
    try:
        await ingest.setup()
        m1, r1 = await ingest.extract("ep1", EPISODE_1, group_id=f"t-{uuid.uuid4().hex[:8]}")
        m2, r2 = await ingest.extract("ep2", EPISODE_2, group_id=f"t-{uuid.uuid4().hex[:8]}")
    finally:
        await ingest.close()

    engine.ingest(m1 + m2, r1 + r2)
    result = engine.resolve()

    assert m1, "Claude should extract at least one entity from episode 1"
    assert result.clusters, "resolution should produce clusters"
    assert graph.read_projection(), "the resolved layer should be projected to Neo4j"
    graph.close()
