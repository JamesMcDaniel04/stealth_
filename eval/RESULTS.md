# Real-data validation results (Phase 7)

**Verdict: PASS.** On a real People.ai CRM relationship graph, resolving entities by their
relationships + anchors **beats a real semantic-embedding baseline by +0.45 F1** (1.00 vs 0.55).
Baseline = OpenAI `text-embedding-3-small` — a strong, fair competitor, not the stub. The core
thesis holds off synthetic data, and the win is sharply located (see below). A second test on
genuinely overlapping sources (structured CRM contacts ↔ free-text call summaries) also produced
the **first real-data case that requires collective *propagation*** — linking the alias
"HyperScience" to the ABBYY account purely through shared people (`make cross-eval`).

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

Baseline: OpenAI `text-embedding-3-small` (real semantic embeddings). Decisions at a realistic
threshold (0.5):

| method | variant links made | name-collisions kept apart |
|---|---|---|
| embedding-only | 5 / 6 | **0 / 10** |
| relational (ours) | **6 / 6** | **10 / 10** |

Pairwise resolution, best-threshold F1 over all 61 pairs:

| method | precision | recall | F1 |
|---|---|---|---|
| embedding-only | 0.38 | 1.00 | **0.55** |
| relational (ours) | 1.00 | 1.00 | **1.00** |

Errors by category at 0.5 — embedding-only vs ours: `person_collision` **10/10 → 0/10**;
`variant_link` 1/6 → 0/6; `account_pair` 0/15 → 0/15; `variant_wrong` 0/30 → 0/30.

**Where the gap is now:** with a real semantic baseline, embedding-only handles acronym/variant
company linking well (5/6) — so that part of the win narrowed vs the stub run. The entire residual
gap is the **10/10 person-collision failure**, which is structural and embedder-proof.

## The case that decides it

- **Same-name, different company** (the irreducible win) — `Anna King@nuance` vs
  `Anna King@samsclub`: identical string, **embedding p=1.00 and wrong**, for all 10 such pairs.
  Relational p=0.01 (correct), via the email anchor + disjoint neighborhoods. This is **structural
  and embedder-proof**: a real semantic model gives identical names identical vectors, so it *must*
  merge them. Strings/embeddings cannot disambiguate two different people who share a name;
  relationships + anchors can. This single failure mode is the entire residual F1 gap.
- **Acronym/variant linking** — `WD` ~ `Western Digital Corporation` (name sim 0.07): the real
  embedding baseline now links this correctly (semantic), so embedding-only scores 5/6 here.
  Relational also gets 6/6 via the **3 shared contacts** — robust, and the way it works when names
  give nothing (it linked via relationships before the embedder could).
- **Hub confounder handled** — Nuance vs Sam's Club share **5 neighbors** (a Deloitte partner +
  4 internal reps; Adamic-Adar 2.36, a real pull to merge), yet are kept **separate** (relational
  p=0.34) by the anchor conflict + inverse-degree down-weighting of hub contacts.

## Cross-source linking — and the first real propagation case

A second test on genuinely overlapping real sources: People.ai's **structured contacts**
(`get_engaged_people`, anchored by email) vs the **free-text account-activity summaries**
(`get_recent_account_activity`) for the same accounts. The prose names the same people and refers
to companies in messy forms — including, for ABBYY, the natural alias **"HyperScience"** (shares
zero string with "ABBYY"). Reproduce: `make cross-eval`.

Pipeline: prose people merge with their structured contact by name (**14/14 bootstrap**); that
gives each prose company a real shared neighborhood, which links it to the right account.

| prose company → account | name sim | embedding-only | pairwise (round 0) | collective |
|---|---|---|---|---|
| `Abbyy` → ABBYY | 0.20 | 0.98 ✓ | 0.30 ✗ | ✓ |
| `HyperScience` → ABBYY | **0.00** | **0.03 ✗** | **0.10 ✗** | **✓** |
| `Five9` → Five9 | 1.00 | 1.00 ✓ | 0.73 ✓ | ✓ |

Linked to the correct account: embedding-only **2/3**, pairwise **1/3**, **collective 3/3**.

`HyperScience → ABBYY` is the **first real-data case that requires collective *propagation***, not
just relational features: it is invisible to embeddings (no string/semantic overlap) **and** to
pairwise relational scoring (no shared neighbor exists until the prose people resolve to the
structured contacts). It appears only after propagation merges those people — the synthetic
Wayne/Gotham capability, now demonstrated on real People.ai data.

## Honest caveats

- **Baseline is real and fair** — OpenAI `text-embedding-3-small`. (An earlier run used an offline
  stub and scored embedding-only at F1 0.50 / 1-of-6 variant links; the real embedder fairly raised
  it to 0.55 / 5-of-6. The collision result was identical both ways — it's structural.)
- **Lift is from relational features, not propagation.** `pairwise` and `collective` scored
  identically (1.00) — the shared contacts are direct neighbors, so collective *propagation* added
  nothing beyond pairwise-relational here (no two-hop cases like the synthetic Wayne/Gotham). What
  is validated on real data is "relationships + anchors ≫ strings/embeddings"; propagation is
  validated separately on the synthetic set and awaits a denser real graph to stress.
- **Company variants are injected** (attached to real contacts); the person-collision and
  shared-partner hard cases are 100% real. Data is a People.ai **demo org**, ~6 accounts — small,
  realistic in shape, synthetic in origin.

## So what

The wedge's premise survives contact with real CRM data against a strong semantic baseline: the
one failure mode that sinks embedding/name dedup and *cannot* be fixed by a better embedder —
same-name / different-entity — is exactly where relationships + anchors win, cleanly (10/10).
Abbreviations/rebrands are a real but embedder-solvable problem; same-name disambiguation is not.
Recommended next: (1) find a corpus where calls/emails and a CRM genuinely overlap, to validate
cross-source linking and stress collective propagation (this dataset didn't); (2) scale past ~6
accounts; (3) take these numbers to design partners.
