# reconcile

**The entity-resolution layer that resolves entities by their _relationships_, not their
strings — and is the only Graph RAG-layer tool that can _un-merge_ a node when new evidence
proves you were wrong.**

`reconcile` sits in front of a Graph RAG store (Graphiti + Neo4j) and does two things nobody
ships at this layer:

1. **Collective resolution** — decides "same entity / different entity" using the
   relationship subgraph (shared neighbors, shared edge types, anchor IDs), not just
   name/embedding similarity. It keeps look-alike-but-distinct entities ("Acme Inc" vs
   "Acme Corp") separate where embedding-only dedup wrongly merges them.
2. **Reversible split with constraint persistence** — when one node turns out to be two
   entities, it splits the node, re-attaches edges correctly, and the human decision
   _survives the next re-ingestion_.

## The load-bearing idea

**The decision store is the source of truth for identity; the graph is a projection of
resolution decisions.** A split is just "add a `cannot_link` constraint + re-project," and
every re-ingestion **replays persisted constraints before writing to the graph**, so a human
decision is never silently overwritten by the next LLM extraction. This is what makes
reversibility possible.

```
Graphiti/LLM extraction ─► Neo4j (:Entity, :RELATES_TO)        [candidates + local rels]
        │ read mentions
        ▼
RESOLUTION  blocking → relational scorer → collective propagation → confidence bands
        │ decisions + evidence
        ▼
DECISION STORE (Postgres)  clusters · must/cannot-link · provenance · scores  ◄─ SOURCE OF TRUTH
        │ project()
        ▼
RECONCILER ─► Neo4j projection (:ResolvedEntity, :RESOLVES_TO)  [graph = projection]
        ▲ re-ingestion REPLAYS constraints before writing
        └─ reversible split = add cannot_link + re-project
```

## Quickstart

```bash
make install        # uv venv + deps
make test           # fast unit/moat tests — no Docker needed
make eval           # Phase 1 gate: collective vs embedding-only on the hard cases
make up             # start Neo4j + Postgres, run migrations  (needs Docker + OPENAI_API_KEY)
make demo           # the defining end-to-end demo
```

`make test` and `make eval` run fully offline (SQLite + a deterministic stub embedder).
`make up` / `make demo` need Docker (copy `.env.example` → `.env`). Postgres is published
on host port **5433** (to avoid clashing with a local Postgres on 5432); Neo4j is on 7687.
An `OPENAI_API_KEY` is only required for live LLM extraction via the Graphiti bridge — the
deterministic demo and tests don't need it.

### Verification status

- **30 unit/moat tests** pass with no Docker (`make test`), including `test_replay.py`
  (a human split survives re-ingestion), `test_retract.py` (undo / latest-decision-wins),
  `test_graphiti_mapping.py` (LLM-extraction mapping via a recorded fixture), and
  `test_sdk.py` / `test_api.py` (SDK + service + auth).
- **Phase 1 gate**: collective F1 **+0.37** over the embedding-only baseline (`make eval`).
- **Real-data validation** (Phase 7, `make real-eval` + `make cross-eval`): on a real People.ai
  CRM graph (10 accounts, 126 contacts) vs a real OpenAI-embedding baseline. The embedder-proof
  win: it keeps same-name/different-company people apart **10/10 vs 0/10** (identical strings give
  identical vectors, so embeddings can't). A cross-source test (CRM contacts ↔ call-summary prose)
  links the alias "HyperScience" and acronym "KKR" to their accounts purely via **shared people**,
  where embeddings and pairwise both fail — collective **7/7** vs embedding **5/7**. See
  [eval/RESULTS.md](eval/RESULTS.md) for the full writeup and honest caveats.
- **Live**: the three-act demo passes against **live Neo4j**; `pytest -m integration` covers a
  live Neo4j projection round-trip and (with keys) a live Claude-extraction smoke test.

## Use it: SDK or service

**In-process SDK** (`from reconcile import Reconciler`):

```python
from reconcile import Reconciler

rec = Reconciler.local()                      # sqlite + in-memory graph, zero deps
rec.ingest(mentions=[
    {"id": "acme-inc",  "name": "Acme Inc",  "type": "Company",
     "attributes": {"domain": "acme.com",     "external_id": "SF-001"}},
    {"id": "acme-corp", "name": "Acme Corp", "type": "Company",
     "attributes": {"domain": "acme-corp.io", "external_id": "SF-002"}},
])
rec.resolve()
rec.same_cluster("acme-inc", "acme-corp")     # False — kept apart by relationships
rec.split("acme-inc", "acme-corp")            # reversible split (persists)
rec.retract("acme-inc", "acme-corp")          # undo — true two-way reversibility
```

`Reconciler()` (no args) reads Postgres/Neo4j/OpenAI from the environment. Run the full
example with `make quickstart` (or `uv run python examples/quickstart.py`).

**HTTP service** (`make serve`, or `docker-compose --profile api up`):

```bash
make serve                                    # uvicorn on :8000 (OpenAPI at /docs)
uv run python examples/http_client.py         # drive it with the Python HTTP client
```

Endpoints: `/ingest`, `/ingest-text` (free-text → Claude extraction), `/resolve`,
`/review-queue`, `/decisions`, `/split`, `/retract`, `/clusters`, `/events`. Set
`RECONCILE_API_TOKEN` to require `Authorization: Bearer <token>` on every call except
`/health`. Dump the spec with `make openapi`.

### Real embeddings & live extraction (optional, needs keys)

- **Embeddings**: with `OPENAI_API_KEY` set, the resolver uses `text-embedding-3-small`
  (cached in Postgres so each name is embedded once); without a key it falls back to the
  offline stub. Tests/eval are unaffected.
- **Extraction**: `rec.ingest_text(name, text)` / `POST /ingest-text` runs free text through
  Graphiti with **Claude** (needs `ANTHROPIC_API_KEY` for the LLM + `OPENAI_API_KEY` for
  Graphiti's embeddings). Try it with `uv run python -m demo.graphiti_demo`. The mapping is
  validated in CI by a recorded fixture (`tests/test_graphiti_mapping.py`) with no live key.

## The defining demo (`make demo`)

1. **Keep-separate.** Collective resolution keeps "Acme Inc" and "Acme Corp" as two entities
   where an embedding-only baseline merges them into one.
2. **Reversible split.** Force a wrong merge, then feed contradicting evidence; the layer
   splits the node back into two and re-attaches edges to the correct side.
3. **Persistence.** Re-ingest a new episode — the split **survives** via constraint replay,
   with zero manual re-fixing.

## Layout

- `src/reconcile/sdk.py` — the `Reconciler` SDK facade. `src/reconcile/client.py` — HTTP client.
- `src/reconcile/resolution/` — blocking, relational features (incl. Adamic–Adar shared
  neighbors), weighted-rule scorer, collective propagation, confidence bander, constrained
  clustering.
- `src/reconcile/store/` — the Postgres decision store (source of truth) + embedding cache.
- `src/reconcile/graph/` — Neo4j adapter, Graphiti/Claude ingest, non-destructive reconciler.
- `src/reconcile/ops/` — `resolve`, reversible `split`, `retract` (undo), constraint `replay`,
  change `events`.
- `src/reconcile/api/` — FastAPI service (auth, OpenAPI). `examples/` — SDK + HTTP usage.
- `eval/hard_cases.yaml` — the hand-built hard-case eval set (the key artifact).
- `demo/` — the defining end-to-end demo (`demo.py`) and the live Claude-extraction demo
  (`graphiti_demo.py`).

> Status: MVP wedge (Phases 0–2). Review-queue UI and packaging are deferred; the API
> endpoints that back the UI are built.
