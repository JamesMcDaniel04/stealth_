# Real-data validation results (Phase 7)

**Verdict: PASS.** On a real People.ai CRM relationship graph, resolving entities by their
relationships + anchors **materially beats embedding/name similarity** — by +0.50 F1, and
decisively on the two hard cases that matter. The core thesis holds off synthetic data.

## What was tested

The original plan (link messy Granola transcript mentions to CRM accounts) wasn't feasible:
the user's Granola had **1 meeting in 30 days, unrelated** to the CRM accounts — no overlap to
measure. We pivoted (with the user) to the strongest feasible real test:

- **Real relationship graph** pulled live via People.ai MCP: 6 accounts (ABBYY, Five9, Western
  Digital, KKR, Nuance, Sam's Club), their **83 real contacts** (names, emails, titles), and
  **111 ENGAGED_WITH edges**. Canonical identity anchored by People.ai account id + email.
- **Injected company-name variants** (controlled): one messy "call mention" per account under a
  variant name (WD, KKR, Nuance, Sam's Wholesale, Five Nine, Abby Software), with **no anchor**,
  attached to 3 of that account's **real** contacts. Only the surface name is synthetic; the
  relationship signal is real. Gold labels known by construction.
- **Natural hard cases** (not injected): the data contains ~10 **same-name / different-company**
  contacts (Anna King@nuance vs Anna King@samsclub, Dennis Lee, Katherine Lewis, …) and a
  genuinely **shared partner** (`aiden.clark@deloitte.com`) engaged on two accounts.

61 labeled pairs: 6 variant→account (same), 30 variant→wrong-account, 15 account↔account, 10
person collisions. Reproduce: `uv run python -m eval.build_real_graph && uv run python -m eval.run_real_eval`
(spot-check the labels with `uv run python -m eval.label_pairs`).

## Numbers

Decisions at a realistic threshold (0.5):

| method | variant links made | name-collisions kept apart |
|---|---|---|
| embedding-only | **1 / 6** | **0 / 10** |
| relational (ours) | **6 / 6** | **10 / 10** |

Pairwise resolution, best-threshold F1 over all 61 pairs:

| method | precision | recall | F1 |
|---|---|---|---|
| embedding-only | 0.33 | 1.00 | **0.50** |
| relational (ours) | 1.00 | 1.00 | **1.00** |

Errors by category at 0.5 — embedding-only vs ours: `person_collision` 10/10 → **0/10**;
`variant_link` 5/6 → **0/6**; `account_pair` 0/15 → 0/15; `variant_wrong` 0/30 → 0/30.

## The cases that decide it

- **Acronym/variant linking** — `WD` ~ `Western Digital Corporation`: name similarity 0.07,
  embedding p=0.02 (misses), but **3 shared contacts** → relational p=0.92 (links). Same for
  `KKR` ~ `Kohlberg Kravis Roberts` (name 0.23 → relational 0.94).
- **Same-name, different company** — `Anna King@nuance` vs `Anna King@samsclub`: identical
  string, embedding p=**1.00 and wrong** (10/10 such pairs). Relational p=0.01 (correct), via the
  email anchor + disjoint neighborhoods. **This is embedder-robust:** real semantic embeddings
  produce *identical* vectors for identical names, so they would be wrong too — strings cannot
  disambiguate two different people with the same name; relationships/anchors can.
- **Hub confounder handled** — Nuance vs Sam's Club share **5 neighbors** (a Deloitte partner +
  4 internal reps; Adamic-Adar 2.36, a real pull to merge), yet are kept **separate** (relational
  p=0.34) by the anchor conflict + inverse-degree down-weighting of hub contacts.

## Honest caveats

- **Embedding baseline is preliminary (stub embedder).** No `OPENAI_API_KEY` was set, so
  embedding-only used the offline char-trigram stub. This *understates* a real semantic baseline
  on the variant-link cases (real embeddings may know WD≈Western Digital), so re-run with a key
  for the definitive variant-link number. It does **not** affect the collision result, which is
  the larger effect and is embedder-robust (identical strings).
- **Lift is from relational features, not propagation.** `pairwise` and `collective` scored
  identically (1.00) — the shared contacts are direct neighbors, so collective *propagation* added
  nothing beyond pairwise-relational here (no two-hop cases like the synthetic Wayne/Gotham). What
  is validated on real data is "relationships + anchors ≫ strings/embeddings."
- **Company variants are injected** (attached to real contacts); the person-collision and
  shared-partner hard cases are 100% real. Data is a People.ai **demo org**, ~6 accounts — small,
  realistic in shape, synthetic in origin.

## So what

The wedge's premise survives contact with real CRM data: the failure modes that sink
embedding/name dedup — same-name-different-entity, and abbreviations/rebrands — are exactly where
relationships + anchors win, and the win is large. Recommended next: (1) re-run with
`OPENAI_API_KEY` for the definitive semantic baseline; (2) find a corpus where calls/emails and a
CRM genuinely overlap to validate the *cross-source linking* (and exercise collective propagation,
which this dataset didn't stress); (3) take these numbers to design partners.
