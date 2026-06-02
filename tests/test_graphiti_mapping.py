"""Graphiti extraction mapping + resolution, validated against a recorded fixture.

No live key needed: we replay a saved AddEpisodeResults shape, map it through the
same code the live path uses, and confirm resolution clusters LLM-extracted data
sensibly (two surface forms of the same company merge; a distinct company stays apart).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from reconcile.embeddings import StubEmbedder
from reconcile.graph import StubGraphStore
from reconcile.graph.graphiti_ingest import map_results
from reconcile.ops import Engine

FIXTURE = Path(__file__).parent / "fixtures" / "graphiti_episode.json"


def _load_results():
    data = json.loads(FIXTURE.read_text())
    nodes = [SimpleNamespace(**n) for n in data["nodes"]]
    edges = [SimpleNamespace(**e) for e in data["edges"]]
    return SimpleNamespace(nodes=nodes, edges=edges)


def test_map_results_shapes_mentions_and_relationships():
    mentions, relationships = map_results(_load_results())
    assert len(mentions) == 5
    assert len(relationships) == 3
    acme = next(m for m in mentions if m.id == "n-acme-1")
    assert acme.name == "Acme Corporation"
    assert acme.entity_type == "Organization"  # "Entity" label is skipped
    assert acme.attributes["industry"] == "manufacturing"
    assert "summary" in acme.attributes


def test_resolution_merges_llm_duplicates(store):
    mentions, relationships = map_results(_load_results())
    engine = Engine(store=store, graph=StubGraphStore(), embedder=StubEmbedder())
    engine.ingest(mentions, relationships)
    engine.resolve()

    # the two surface forms of the same company resolve together...
    assert engine.same_cluster("n-acme-1", "n-acme-2")
    # ...the distinct company does not, and people aren't merged
    assert not engine.same_cluster("n-acme-1", "n-globex")
    assert not engine.same_cluster("n-jane", "n-bob")
