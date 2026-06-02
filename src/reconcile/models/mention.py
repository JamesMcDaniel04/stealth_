"""A Mention is a raw extracted entity candidate plus its local relationships.

Mentions are what the resolver works on. Identity (which mentions are the *same*
real-world entity) is decided by clustering — never baked into the mention itself.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Mention(BaseModel):
    id: str
    name: str
    entity_type: str = "Entity"
    # Anchor / disambiguating attributes: domain, external_id (e.g. Salesforce ID), etc.
    attributes: dict[str, str] = Field(default_factory=dict)
    # Source episode/document this mention was extracted from.
    source: str = ""

    def anchor(self, key: str) -> str | None:
        v = self.attributes.get(key)
        return v.strip().lower() if isinstance(v, str) and v.strip() else None


class Relationship(BaseModel):
    """A local edge between two mentions, e.g. (Acme)-[EMPLOYS]->(Jane)."""

    src: str
    dst: str
    edge_type: str = "RELATES_TO"
