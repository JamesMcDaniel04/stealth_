"""Embedder protocol with an OpenAI implementation and a deterministic stub.

The stub lets eval + unit tests run offline with reproducible vectors. It is a
hash-based bag-of-character-trigrams embedding: cheap, deterministic, and good
enough that semantically similar short strings ("Acme Inc" / "Acme Incorporated")
land near each other while distinct strings do not.
"""

from __future__ import annotations

import hashlib
from typing import Protocol

import numpy as np

_DIM = 256


class Embedder(Protocol):
    def embed(self, text: str) -> np.ndarray: ...


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


class StubEmbedder:
    """Deterministic, offline, hash-of-trigrams embedder."""

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


class OpenAIEmbedder:
    """Thin wrapper over OpenAI embeddings; falls back to stub when no key is set."""

    dim = 1536

    def __init__(self, api_key: str, model: str = "text-embedding-3-small"):
        self._key = api_key
        self._model = model
        self._fallback = StubEmbedder()

    def embed(self, text: str) -> np.ndarray:
        if not self._key:
            return self._fallback.embed(text)
        import httpx

        resp = httpx.post(
            "https://api.openai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {self._key}"},
            json={"input": text or " ", "model": self._model},
            timeout=30,
        )
        resp.raise_for_status()
        return np.array(resp.json()["data"][0]["embedding"], dtype=np.float64)


def default_embedder() -> Embedder:
    """StubEmbedder by default so nothing requires network unless explicitly wired."""
    return StubEmbedder()
