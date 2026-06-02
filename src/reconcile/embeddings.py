"""Embedders: a deterministic offline stub, a real OpenAI embedder, and a
persistent cache wrapper so each distinct string is embedded (and paid for) once.

`make_embedder()` picks OpenAI when a key is configured, else the stub — so unit
tests and offline eval keep working with zero network, while the running system
uses real semantic embeddings when a key is present.
"""

from __future__ import annotations

import hashlib
from typing import Protocol, runtime_checkable

import numpy as np

from reconcile.config import Settings, get_settings

_DIM = 256


@runtime_checkable
class Embedder(Protocol):
    model_id: str

    def embed(self, text: str) -> np.ndarray: ...


class EmbeddingCache(Protocol):
    """Backing store for cached vectors (implemented by DecisionStore)."""

    def get_embedding(self, key: str) -> np.ndarray | None: ...
    def put_embedding(self, key: str, vector: np.ndarray) -> None: ...


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


class StubEmbedder:
    """Deterministic, offline, hash-of-trigrams embedder."""

    model_id = "stub-trigram-v1"
    dim = _DIM

    def embed(self, text: str) -> np.ndarray:
        text = (text or "").lower().strip()
        vec = np.zeros(self.dim, dtype=np.float64)
        padded = f"  {text}  "
        for i in range(len(padded) - 2):
            tri = padded[i : i + 3]
            h = int(hashlib.md5(tri.encode()).hexdigest(), 16)
            vec[h % self.dim] += 1.0
        norm = np.linalg.norm(vec)
        return vec / norm if norm else vec

    def embed_batch(self, texts: list[str]) -> list[np.ndarray]:
        return [self.embed(t) for t in texts]


class OpenAIEmbedder:
    """OpenAI embeddings via the HTTP API, with batch support and a stub fallback."""

    dim = 1536

    def __init__(self, api_key: str, model: str = "text-embedding-3-small"):
        self._key = api_key
        self._model = model
        self.model_id = f"openai:{model}"
        self._fallback = StubEmbedder()

    def embed(self, text: str) -> np.ndarray:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[np.ndarray]:
        if not self._key:
            return self._fallback.embed_batch(texts)
        import httpx

        inputs = [t or " " for t in texts]
        for attempt in range(3):
            try:
                resp = httpx.post(
                    "https://api.openai.com/v1/embeddings",
                    headers={"Authorization": f"Bearer {self._key}"},
                    json={"input": inputs, "model": self._model},
                    timeout=30,
                )
                resp.raise_for_status()
                data = sorted(resp.json()["data"], key=lambda d: d["index"])
                return [np.array(d["embedding"], dtype=np.float64) for d in data]
            except httpx.HTTPError:
                if attempt == 2:
                    raise
        raise RuntimeError("unreachable")


class CachedEmbedder:
    """Wraps an embedder with a persistent cache keyed by (model_id, text)."""

    def __init__(self, inner: Embedder, cache: EmbeddingCache):
        self._inner = inner
        self._cache = cache
        self.model_id = inner.model_id

    def _key(self, text: str) -> str:
        raw = f"{self._inner.model_id}\x00{text or ''}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def embed(self, text: str) -> np.ndarray:
        key = self._key(text)
        cached = self._cache.get_embedding(key)
        if cached is not None:
            return cached
        vec = self._inner.embed(text)
        self._cache.put_embedding(key, vec)
        return vec


def make_embedder(settings: Settings | None = None) -> Embedder:
    """OpenAI when configured, else the offline stub."""
    s = settings or get_settings()
    if s.embedding_provider == "openai" and s.openai_api_key:
        return OpenAIEmbedder(s.openai_api_key, s.embedding_model)
    return StubEmbedder()


def default_embedder() -> Embedder:
    """Stub by default so nothing requires network unless explicitly wired."""
    return StubEmbedder()
