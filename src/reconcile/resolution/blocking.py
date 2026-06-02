"""Blocking — generate candidate pairs to avoid O(n^2) all-pairs scoring.

Blocks on three keys, union of which forms the candidate set:
  1. shared normalized name token  (catches "Acme Inc" / "Acme Corp")
  2. shared anchor value           (catches rebrands with a common external_id)
  3. shared relationship neighbor  (catches aliases discoverable only relationally)

The relational block is what lets the collective step expand candidates as merges
accumulate — see CollectiveResolver, which re-blocks on cluster-mapped neighbors.
"""

from __future__ import annotations

import re
from itertools import combinations

from reconcile.models import Mention
from reconcile.resolution.features import ANCHOR_KEYS, FeatureContext

_STOPWORDS = {"inc", "corp", "corporation", "llc", "ltd", "co", "the", "group", "holdings"}
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _name_tokens(name: str) -> set[str]:
    toks = {t for t in _TOKEN_RE.findall(name.lower()) if len(t) > 1 and t not in _STOPWORDS}
    return toks


def candidate_pairs(
    mentions: list[Mention],
    ctx: FeatureContext,
    neighbor_map: dict[str, str] | None = None,
) -> set[tuple[str, str]]:
    blocks: dict[str, set[str]] = {}

    def add(key: str, mid: str) -> None:
        blocks.setdefault(key, set()).add(mid)

    for m in mentions:
        # only ever resolve within an entity type
        for tok in _name_tokens(m.name):
            add(f"name:{m.entity_type}:{tok}", m.id)
        for k in ANCHOR_KEYS:
            v = m.anchor(k)
            if v:
                add(f"anchor:{k}:{v}", m.id)
        for nb in ctx._mapped_neighbors(m.id, neighbor_map):
            add(f"nbr:{m.entity_type}:{nb}", m.id)

    pairs: set[tuple[str, str]] = set()
    for members in blocks.values():
        if len(members) < 2:
            continue
        for a, b in combinations(sorted(members), 2):
            if ctx.mentions[a].entity_type == ctx.mentions[b].entity_type:
                pairs.add((a, b))
    return pairs
