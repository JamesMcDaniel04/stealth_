"""Embedder factory + persistent cache behavior."""

from __future__ import annotations

import numpy as np

from reconcile.config import Settings
from reconcile.embeddings import CachedEmbedder, StubEmbedder, make_embedder


def test_make_embedder_defaults_to_stub_without_key():
    emb = make_embedder(Settings(openai_api_key="", embedding_provider="openai"))
    assert isinstance(emb, StubEmbedder)


def test_make_embedder_uses_openai_with_key():
    from reconcile.embeddings import OpenAIEmbedder

    emb = make_embedder(Settings(openai_api_key="sk-test", embedding_provider="openai"))
    assert isinstance(emb, OpenAIEmbedder)
    assert emb.model_id.startswith("openai:")


def test_cached_embedder_persists_and_reuses(store):
    calls = {"n": 0}

    class CountingStub(StubEmbedder):
        model_id = "counting-stub"

        def embed(self, text: str) -> np.ndarray:
            calls["n"] += 1
            return super().embed(text)

    cached = CachedEmbedder(CountingStub(), store)
    v1 = cached.embed("Acme Inc")
    v2 = cached.embed("Acme Inc")  # served from cache, no second inner call
    assert calls["n"] == 1
    assert np.allclose(v1, v2)

    # a fresh CachedEmbedder over the same store also hits the cache
    cached2 = CachedEmbedder(CountingStub(), store)
    cached2.embed("Acme Inc")
    assert calls["n"] == 1
