"""Graphiti bridge — the reference integration for live LLM extraction.

Graphiti (graphiti-core) does the extraction we deliberately do NOT build: it reads
free text and writes :Entity nodes + :RELATES_TO edges into Neo4j. This bridge runs
an episode through Graphiti, then *harvests* those nodes into our Mention /
Relationship model so the resolution layer can resolve them.

The reproducible demo ingests from a fixed dataset (no LLM, no API cost) so it can
be screen-recorded deterministically; this bridge is the path for real documents.
Requires OPENAI_API_KEY and a running Neo4j.
"""

from __future__ import annotations

from datetime import UTC, datetime

from reconcile.config import get_settings
from reconcile.models import Mention, Relationship


class GraphitiIngest:
    def __init__(self, uri: str | None = None, user: str | None = None,
                 password: str | None = None):
        from graphiti_core import Graphiti

        s = get_settings()
        if not s.openai_api_key:
            raise RuntimeError(
                "GraphitiIngest needs OPENAI_API_KEY for LLM extraction. "
                "For an offline run use the dataset ingestion path (see demo/demo.py)."
            )
        self._graphiti = Graphiti(
            uri or s.neo4j_uri, user or s.neo4j_user, password or s.neo4j_password
        )

    async def setup(self) -> None:
        await self._graphiti.build_indices_and_constraints()

    async def add_episode(self, name: str, text: str, group_id: str = "reconcile") -> None:
        from graphiti_core.nodes import EpisodeType

        await self._graphiti.add_episode(
            name=name,
            episode_body=text,
            source=EpisodeType.text,
            source_description="reconcile ingest",
            reference_time=datetime.now(UTC),
            group_id=group_id,
        )

    async def harvest(
        self, group_id: str = "reconcile"
    ) -> tuple[list[Mention], list[Relationship]]:
        """Read Graphiti's extracted entities/edges into our Mention/Relationship model."""
        driver = self._graphiti.driver
        async with driver.session() as sess:
            ents = await sess.run(
                "MATCH (e:Entity) WHERE e.group_id = $g "
                "RETURN e.uuid AS id, e.name AS name, "
                "coalesce(e.summary, '') AS summary",
                g=group_id,
            )
            mentions = [
                Mention(id=r["id"], name=r["name"], entity_type="Entity",
                        attributes={"summary": r["summary"][:200]} if r["summary"] else {})
                async for r in ents
            ]
            rels_res = await sess.run(
                "MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity) "
                "WHERE a.group_id = $g AND b.group_id = $g "
                "RETURN a.uuid AS src, b.uuid AS dst, coalesce(r.name, 'RELATES_TO') AS kind",
                g=group_id,
            )
            relationships = [
                Relationship(src=r["src"], dst=r["dst"], edge_type=r["kind"])
                async for r in rels_res
            ]
        return mentions, relationships

    async def close(self) -> None:
        await self._graphiti.close()
