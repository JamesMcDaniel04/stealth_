"""HTTP client example — drive a running reconcile service over HTTP.

Start the service first:  make serve   (optionally set RECONCILE_API_TOKEN)
Then run:                 uv run python examples/http_client.py
"""

from __future__ import annotations

import os

from reconcile.client import ReconcileClient

client = ReconcileClient(
    base_url=os.environ.get("RECONCILE_URL", "http://localhost:8000"),
    token=os.environ.get("RECONCILE_API_TOKEN", ""),
)

print("health:", client.health())

client.ingest(
    mentions=[
        {"id": "m1", "name": "Acme", "type": "Company", "attributes": {"domain": "acme.com"}},
        {"id": "m2", "name": "Acme", "type": "Company", "attributes": {"domain": "acme.com"}},
    ],
)
print("resolve:", client.resolve()["clusters"])
print("split:", client.split("m1", "m2", evidence={"reason": "distinct"})["clusters"])
print("retract:", client.retract("m1", "m2")["clusters"])
print("events:", client.events())

client.close()
