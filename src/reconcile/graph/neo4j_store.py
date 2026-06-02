"""Live Neo4j GraphStore.

Source entities are :Entity nodes joined by :RELATES_TO {kind}. The resolved
identity layer is a *separate*, non-destructive projection:

    (:Entity)-[:RESOLVES_TO]->(:ResolvedEntity {cluster_id})
    (:ResolvedEntity)-[:RESOLVED_REL {kind}]->(:ResolvedEntity)

project() rebuilds only the :ResolvedEntity layer, so a merge or split never
touches the underlying extracted graph — it just rewires the projection.
"""

from __future__ import annotations

from reconcile.config import get_settings
from reconcile.models import Cluster, Mention, Relationship


class Neo4jStore:
    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
    ) -> None:
        from neo4j import GraphDatabase

        s = get_settings()
        self._driver = GraphDatabase.driver(
            uri or s.neo4j_uri,
            auth=(user or s.neo4j_user, password or s.neo4j_password),
        )
        self._ensure_constraints()

    def _ensure_constraints(self) -> None:
        with self._driver.session() as sess:
            sess.run("CREATE CONSTRAINT entity_id IF NOT EXISTS "
                     "FOR (e:Entity) REQUIRE e.id IS UNIQUE")
            sess.run("CREATE CONSTRAINT resolved_id IF NOT EXISTS "
                     "FOR (r:ResolvedEntity) REQUIRE r.cluster_id IS UNIQUE")

    # --- input ------------------------------------------------------------
    def upsert_entities(self, mentions: list[Mention]) -> None:
        rows = [
            {"id": m.id, "name": m.name, "type": m.entity_type, "attrs": dict(m.attributes),
             "source": m.source}
            for m in mentions
        ]
        with self._driver.session() as sess:
            sess.run(
                """
                UNWIND $rows AS row
                MERGE (e:Entity {id: row.id})
                SET e.name = row.name, e.type = row.type,
                    e.attrs = row.attrs, e.source = row.source
                """,
                rows=rows,
            )

    def upsert_relationships(self, relationships: list[Relationship]) -> None:
        rows = [{"src": r.src, "dst": r.dst, "kind": r.edge_type} for r in relationships]
        with self._driver.session() as sess:
            sess.run(
                """
                UNWIND $rows AS row
                MATCH (a:Entity {id: row.src}), (b:Entity {id: row.dst})
                MERGE (a)-[rel:RELATES_TO {kind: row.kind}]->(b)
                """,
                rows=rows,
            )

    def read_entities(self) -> list[Mention]:
        with self._driver.session() as sess:
            res = sess.run("MATCH (e:Entity) RETURN e.id AS id, e.name AS name, "
                           "e.type AS type, e.attrs AS attrs, e.source AS source")
            return [
                Mention(
                    id=r["id"], name=r["name"], entity_type=r["type"] or "Entity",
                    attributes={k: str(v) for k, v in (r["attrs"] or {}).items()},
                    source=r["source"] or "",
                )
                for r in res
            ]

    def read_relationships(self) -> list[Relationship]:
        with self._driver.session() as sess:
            res = sess.run("MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity) "
                           "RETURN a.id AS src, b.id AS dst, r.kind AS kind")
            return [Relationship(src=r["src"], dst=r["dst"], edge_type=r["kind"]) for r in res]

    # --- output: the resolved projection ----------------------------------
    def project(
        self, clusters: list[Cluster], resolved_edges: set[tuple[str, str, str]]
    ) -> None:
        cluster_rows = [
            {"cid": c.cluster_id, "members": sorted(c.members), "attrs": dict(c.attributes)}
            for c in clusters
        ]
        edge_rows = [{"a": a, "kind": k, "b": b} for (a, k, b) in resolved_edges]
        with self._driver.session() as sess:
            # idempotent rebuild of the resolved layer only
            sess.run("MATCH (r:ResolvedEntity) DETACH DELETE r")
            sess.run(
                """
                UNWIND $rows AS row
                CREATE (r:ResolvedEntity {cluster_id: row.cid})
                SET r.attrs = row.attrs
                WITH r, row
                UNWIND row.members AS mid
                MATCH (e:Entity {id: mid})
                MERGE (e)-[:RESOLVES_TO]->(r)
                """,
                rows=cluster_rows,
            )
            sess.run(
                """
                UNWIND $rows AS row
                MATCH (a:ResolvedEntity {cluster_id: row.a}),
                      (b:ResolvedEntity {cluster_id: row.b})
                MERGE (a)-[:RESOLVED_REL {kind: row.kind}]->(b)
                """,
                rows=edge_rows,
            )

    def read_projection(self) -> dict[str, set[str]]:
        with self._driver.session() as sess:
            res = sess.run(
                "MATCH (e:Entity)-[:RESOLVES_TO]->(r:ResolvedEntity) "
                "RETURN r.cluster_id AS cid, collect(e.id) AS members"
            )
            return {r["cid"]: set(r["members"]) for r in res}

    def resolved_relationships(self) -> set[tuple[str, str, str]]:
        with self._driver.session() as sess:
            res = sess.run(
                "MATCH (a:ResolvedEntity)-[r:RESOLVED_REL]->(b:ResolvedEntity) "
                "RETURN a.cluster_id AS a, r.kind AS kind, b.cluster_id AS b"
            )
            return {(r["a"], r["kind"], r["b"]) for r in res}

    def clear(self) -> None:
        with self._driver.session() as sess:
            sess.run("MATCH (n) WHERE n:Entity OR n:ResolvedEntity DETACH DELETE n")

    def close(self) -> None:
        self._driver.close()
