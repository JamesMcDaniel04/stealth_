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
Only `make up` / `make demo` need Docker and an `OPENAI_API_KEY` (copy `.env.example` → `.env`).

## The defining demo (`make demo`)

1. **Keep-separate.** Collective resolution keeps "Acme Inc" and "Acme Corp" as two entities
   where an embedding-only baseline merges them into one.
2. **Reversible split.** Force a wrong merge, then feed contradicting evidence; the layer
   splits the node back into two and re-attaches edges to the correct side.
3. **Persistence.** Re-ingest a new episode — the split **survives** via constraint replay,
   with zero manual re-fixing.

## Layout

- `src/reconcile/resolution/` — blocking, relational features, weighted-rule scorer,
  collective propagation, confidence bander, constrained clustering.
- `src/reconcile/store/` — the Postgres decision store (source of truth).
- `src/reconcile/graph/` — Neo4j adapter, Graphiti ingest, non-destructive reconciler.
- `src/reconcile/ops/` — `resolve`, reversible `split`, constraint `replay`, change `events`.
- `eval/hard_cases.yaml` — the hand-built hard-case eval set (the key artifact).
- `demo/` — the defining end-to-end demo.

> Status: MVP wedge (Phases 0–2). Review-queue UI and packaging are deferred; the API
> endpoints that back the UI are built.
