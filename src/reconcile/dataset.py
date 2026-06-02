"""Load a YAML dataset (mentions + relationships [+ labeled pairs]) into domain objects.

Shared by the eval harness and the demo so both speak the same format.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from reconcile.models import Mention, Relationship


@dataclass
class LabeledPair:
    a: str
    b: str
    label: str  # "same" | "different"
    trap: str = ""

    @property
    def gold_same(self) -> bool:
        return self.label == "same"


@dataclass
class Dataset:
    mentions: list[Mention]
    relationships: list[Relationship]
    pairs: list[LabeledPair] = field(default_factory=list)


def load_dataset(path: str | Path) -> Dataset:
    data = yaml.safe_load(Path(path).read_text())
    mentions = [
        Mention(
            id=m["id"],
            name=m["name"],
            entity_type=m.get("type", "Entity"),
            attributes={k: str(v) for k, v in (m.get("attributes") or {}).items()},
            source=m.get("source", ""),
        )
        for m in data.get("mentions", [])
    ]
    relationships = [
        Relationship(src=r["src"], dst=r["dst"], edge_type=r.get("type", "RELATES_TO"))
        for r in data.get("relationships", [])
    ]
    pairs = [
        LabeledPair(a=p["a"], b=p["b"], label=p["label"], trap=p.get("trap", ""))
        for p in data.get("pairs", [])
    ]
    return Dataset(mentions=mentions, relationships=relationships, pairs=pairs)
