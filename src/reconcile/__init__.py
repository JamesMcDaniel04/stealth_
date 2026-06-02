"""reconcile — collective + reversible entity-resolution layer for Graph RAG."""

__version__ = "0.1.0"

from reconcile.models import Mention, Relationship
from reconcile.sdk import Reconciler

__all__ = ["Reconciler", "Mention", "Relationship", "__version__"]
