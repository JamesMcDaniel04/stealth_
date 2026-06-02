"""`ReconcileClient` — a thin Python client for the reconcile HTTP service.

Lets a caller drive a running reconcile service without importing the engine:

    from reconcile.client import ReconcileClient
    c = ReconcileClient("http://localhost:8000", token="...")
    c.ingest(mentions=[...], relationships=[...])
    c.resolve()
    c.split("acme-inc", "acme-corp")
    c.retract("acme-inc", "acme-corp")
"""

from __future__ import annotations

from typing import Any

import httpx


class ReconcileClient:
    def __init__(self, base_url: str = "http://localhost:8000", token: str = "", timeout: float = 30):
        self._base = base_url.rstrip("/")
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._http = httpx.Client(base_url=self._base, headers=headers, timeout=timeout)

    def _post(self, path: str, json: dict | None = None) -> Any:
        r = self._http.post(path, json=json or {})
        r.raise_for_status()
        return r.json()

    def _get(self, path: str) -> Any:
        r = self._http.get(path)
        r.raise_for_status()
        return r.json()

    def health(self) -> dict:
        return self._get("/health")

    def ingest(
        self, mentions: list[dict] | None = None, relationships: list[dict] | None = None
    ) -> dict:
        return self._post("/ingest", {"mentions": mentions or [], "relationships": relationships or []})

    def ingest_text(self, name: str, text: str) -> dict:
        return self._post("/ingest-text", {"name": name, "text": text})

    def resolve(self) -> dict:
        return self._post("/resolve")

    def review_queue(self) -> list[dict]:
        return self._get("/review-queue")

    def submit_decision(self, a: str, b: str, same: bool, evidence: dict | None = None) -> dict:
        return self._post("/decisions", {"a": a, "b": b, "same": same, "evidence": evidence or {}})

    def split(self, a: str, b: str, evidence: dict | None = None) -> dict:
        return self._post("/split", {"a": a, "b": b, "evidence": evidence or {}})

    def retract(self, a: str, b: str) -> dict:
        return self._post("/retract", {"a": a, "b": b})

    def clusters(self) -> list[dict]:
        return self._get("/clusters")

    def events(self) -> list[dict]:
        return self._get("/events")

    def close(self) -> None:
        self._http.close()
