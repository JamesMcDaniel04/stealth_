"""Diff two cluster assignments into SPLIT / MERGE change events.

Emitted so downstream consumers learn that stable ids split or merged between runs.
"""

from __future__ import annotations

from reconcile.models import ChangeEvent, Cluster, EventKind


def diff_events(prev: list[Cluster], new: list[Cluster]) -> list[ChangeEvent]:
    events: list[ChangeEvent] = []

    new_owner = {m: c.cluster_id for c in new for m in c.members}
    prev_owner = {m: c.cluster_id for c in prev for m in c.members}

    # SPLIT: a previous cluster whose members now span more than one new cluster
    for pc in prev:
        targets = {new_owner[m] for m in pc.members if m in new_owner}
        if len(targets) > 1:
            events.append(
                ChangeEvent(
                    kind=EventKind.SPLIT,
                    old_ids=[pc.cluster_id],
                    new_ids=sorted(targets),
                )
            )

    # MERGE: a new cluster that absorbed members from more than one previous cluster
    for nc in new:
        sources = {prev_owner[m] for m in nc.members if m in prev_owner}
        if len(sources) > 1:
            events.append(
                ChangeEvent(
                    kind=EventKind.MERGE,
                    old_ids=sorted(sources),
                    new_ids=[nc.cluster_id],
                )
            )

    return events
