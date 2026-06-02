"""Constraint replay.

Replay is not a separate pass — it is the invariant that the resolver loads every
persisted constraint and applies it (cannot-link first) *before* writing to the
graph. This module names that invariant and provides the loader the Engine uses, so
the moat behavior is explicit and testable rather than implicit in resolve().
"""

from __future__ import annotations

from reconcile.models import ConstraintRecord
from reconcile.store import DecisionStore


def load_constraints(store: DecisionStore) -> list[ConstraintRecord]:
    """All active constraints, to be applied before any graph write on every run."""
    return store.get_constraints(active_only=True)
