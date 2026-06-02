from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from reconcile.dataset import load_dataset
from reconcile.embeddings import StubEmbedder
from reconcile.resolution.features import FeatureContext
from reconcile.store import DecisionStore

HARD_CASES = Path(__file__).resolve().parents[1] / "eval" / "hard_cases.yaml"


@pytest.fixture
def store(tmp_path) -> DecisionStore:
    url = f"sqlite:///{tmp_path / (uuid.uuid4().hex + '.db')}"
    return DecisionStore(url=url, create=True)


@pytest.fixture
def hard_cases():
    return load_dataset(HARD_CASES)


@pytest.fixture
def feature_ctx(hard_cases) -> FeatureContext:
    return FeatureContext.build(
        hard_cases.mentions, hard_cases.relationships, embedder=StubEmbedder()
    )
