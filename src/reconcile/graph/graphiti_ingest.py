"""Graphiti bridge — the reference integration for live LLM extraction.

Graphiti (graphiti-core) does the extraction we deliberately do NOT build: it reads
free text and extracts entities + relationships. This bridge runs an episode through
Graphiti (LLM = Claude/Anthropic, embeddings = OpenAI), then maps the returned
`AddEpisodeResults` into our Mention / Relationship model so the resolution layer can
resolve them — and our reversible split / replay applies on top.

Requires ANTHROPIC_API_KEY (extraction) and OPENAI_API_KEY (Graphiti's embeddings).
The mapping (`map_results`) is pure and is unit-tested against a recorded fixture, so
the integration shape is verified in CI without any live key.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from reconcile.config import get_settings
from reconcile.models import Mention, Relationship


def _stringify_attrs(attrs: dict[str, Any] | None, summary: str | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in (attrs or {}).items():
        if v is not None:
            out[k] = str(v)
    if summary:
        out["summary"] = str(summary)[:200]
    return out


def map_results(results: Any) -> tuple[list[Mention], list[Relationship]]:
    """Map a Graphiti `AddEpisodeResults` (or any object with `.nodes`/`.edges`) to
    our Mention/Relationship model. Pure + duck-typed so it's testable from a fixture.
    """
    mentions: list[Mention] = []
    for node in getattr(results, "nodes", []):
        labels = getattr(node, "labels", None) or []
        entity_type = next((label for label in labels if label != "Entity"), "Entity")
        mentions.append(
            Mention(
                id=getattr(node, "uuid"),
                name=getattr(node, "name"),
                entity_type=entity_type,
                attributes=_stringify_attrs(
                    getattr(node, "attributes", None), getattr(node, "summary", None)
                ),
                source=getattr(node, "group_id", "") or "",
            )
        )

    relationships: list[Relationship] = []
    for edge in getattr(results, "edges", []):
        relationships.append(
            Relationship(
                src=getattr(edge, "source_node_uuid"),
                dst=getattr(edge, "target_node_uuid"),
                edge_type=getattr(edge, "name", None) or "RELATES_TO",
            )
        )
    return mentions, relationships


class GraphitiIngest:
    """Live extraction via Graphiti with Claude (LLM) + OpenAI (embeddings)."""

    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
    ):
        from graphiti_core import Graphiti
        from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
        from graphiti_core.llm_client.anthropic_client import AnthropicClient
        from graphiti_core.llm_client.config import LLMConfig

        s = get_settings()
        if not s.anthropic_api_key:
            raise RuntimeError(
                "GraphitiIngest needs ANTHROPIC_API_KEY for Claude extraction. "
                "For an offline run use the dataset ingestion path (see demo/demo.py)."
            )
        if not s.openai_api_key:
            raise RuntimeError("GraphitiIngest needs OPENAI_API_KEY for Graphiti's embeddings.")

        llm = AnthropicClient(config=LLMConfig(api_key=s.anthropic_api_key, model=s.anthropic_model))
        embedder = OpenAIEmbedder(
            config=OpenAIEmbedderConfig(api_key=s.openai_api_key, embedding_model=s.embedding_model)
        )
        self._graphiti = Graphiti(
            uri or s.neo4j_uri,
            user or s.neo4j_user,
            password or s.neo4j_password,
            llm_client=llm,
            embedder=embedder,
        )

    async def setup(self) -> None:
        await self._graphiti.build_indices_and_constraints()

    async def add_episode(self, name: str, text: str, group_id: str = "reconcile"):
        from graphiti_core.nodes import EpisodeType

        return await self._graphiti.add_episode(
            name=name,
            episode_body=text,
            source=EpisodeType.text,
            source_description="reconcile ingest",
            reference_time=datetime.now(UTC),
            group_id=group_id,
        )

    async def extract(
        self, name: str, text: str, group_id: str = "reconcile"
    ) -> tuple[list[Mention], list[Relationship]]:
        """Run one episode through Claude extraction and return mapped mentions/edges."""
        results = await self.add_episode(name, text, group_id)
        return map_results(results)

    async def close(self) -> None:
        await self._graphiti.close()


async def ingest_text(engine, name: str, text: str, group_id: str = "reconcile"):
    """Convenience: extract free text via Claude, ingest, and resolve.

    `engine` is a reconcile Engine. Returns its ResolveResult.
    """
    ingest = GraphitiIngest()
    try:
        await ingest.setup()
        mentions, relationships = await ingest.extract(name, text, group_id)
    finally:
        await ingest.close()
    engine.ingest(mentions, relationships)
    return engine.resolve()
