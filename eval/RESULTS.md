# Real-data validation results (Phase 7)

**Verdict: PASS.** On a real People.ai CRM relationship graph (**10 accounts, 126 contacts**),
resolving entities by relationships + anchors beats a real semantic-embedding baseline
(OpenAI `text-embedding-3-small`). The decisive, scale-invariant result: it disambiguates
**same-name / different-company** people **10/10** where embedding-only is confidently wrong
**10/10** — a failure no better embedder can fix (identical strings → identical vectors). A second
test on genuinely overlapping sources (structured CRM contacts ↔ free-text call summaries)
produced **two real cases that require collective *propagation*** — linking the alias
"HyperScience" and the acronym "KKR" to their accounts purely through shared people, where both
embeddings and pairwise scoring fail (`make cross-eval`).

## What was tested

The original plan (link messy Granola transcript mentions to CRM accounts) wasn't feasible:
the user's Granola had **1 meeting in 30 days, unrelated** to the CRM accounts — no overlap to
measure. We pivoted (with the user) to the strongest feasible real test:

- **Real relationship graph** pulled live via People.ai MCP: **10 accounts** (ABBYY, Five9,
  Western Digital, KKR, Nuance, Sam's Club, Twitch, NBCUniversal, Commonwealth, Mars Veterinary),
  their **126 real contacts** (names, emails, titles), and **171 ENGAGED_WITH edges**. Canonical
  identity anchored by People.ai account id + email.
- **Injected company-name variants** (controlled): one messy "call mention" per account under a
  variant name (WD, KKR, NBCU, Mars Vet, …), with **no anchor**, attached to 3 of that account's
  **real** contacts. Only the surface name is synthetic; the relationship signal is real.
- **Natural hard cases** (not injected): ~10 **same-name / different-company** contacts
  (Anna King@nuance vs Anna King@samsclub, Dennis Lee, Katherine Lewis, …) and a genuinely
  **shared partner** (`aiden.clark@deloitte.com`) engaged on two accounts.

155 labeled pairs (10 variant→account, 90 variant→wrong, 45 account↔account, 10 person
collisions). Reproduce: `make real-eval` (spot-check labels with `uv run python -m eval.label_pairs`).

## Numbers

Baseline: OpenAI `text-embedding-3-small` (real semantic embeddings). The decisive, **scale-
invariant** result is per category at a realistic threshold (0.5) — embedding-only vs ours:

| hard case | count | embedding-only wrong | ours wrong |
|---|---|---|---|
| same-name / different company | 10 | **10 (all)** | **0** |
| company variant → its account | 10 | 1 | 0 |
| distinct accounts (incl. shared rep/partner) | 45 | 0 | 0 |
| variant → wrong account | 90 | 0 | 0 |

Best-threshold F1 over all 155 pairs: embedding-only **0.67**, ours **1.00** (**+0.33**). The
aggregate gap *shrinks* as you add accounts — more distinct accounts add easy negatives that
embeddings handle — which is itself the finding: **with a strong embedder, the durable,
embedder-proof win is same-name disambiguation (10/10), not abbreviation linking** (embeddings do
that fine). The other structural win is propagation — see below.

## The case that decides it

- **Same-name, different company** (the irreducible win) — `Anna King@nuance` vs
  `Anna King@samsclub`: identical string, **embedding p=1.00 and wrong**, for all 10 such pairs.
  Relational p=0.01 (correct), via the email anchor + disjoint neighborhoods. This is **structural
  and embedder-proof**: a real semantic model gives identical names identical vectors, so it *must*
  merge them. Strings/embeddings cannot disambiguate two different people who share a name;
  relationships + anchors can. This single failure mode is the entire residual F1 gap.
- **Acronym/variant linking** — `WD` ~ `Western Digital Corporation` (name sim 0.07): the real
  embedding baseline now links most of these (9/10) semantically. Relational gets 10/10 via the
  **3 shared contacts** — robust, and the way it works when names give nothing (it linked via
  relationships before the embedder could). The acronym `KKR` (cross-source test) is one the
  embedder still misses — see propagation below.
- **Hub confounder handled** — Nuance vs Sam's Club share **5 neighbors** (a Deloitte partner +
  4 internal reps; Adamic-Adar 2.36, a real pull to merge), yet are kept **separate** (relational
  p=0.34) by the anchor conflict + inverse-degree down-weighting of hub contacts.

## Cross-source linking — and the first real propagation case

A second test on genuinely overlapping real sources: People.ai's **structured contacts**
(`get_engaged_people`, anchored by email) vs the **free-text account-activity summaries**
(`get_recent_account_activity`) for the same accounts. The prose names the same people and refers
to companies in messy forms — including, for ABBYY, the natural alias **"HyperScience"** (shares
zero string with "ABBYY"). Reproduce: `make cross-eval`.

4 prose accounts, 7 company surface forms, 27 prose person-mentions. Pipeline: prose people merge
with their structured contact by name (**27/27 bootstrap**); that gives each prose company a real
shared neighborhood, which links it to the right account.

| prose company → account | name sim | embedding-only | pairwise (round 0) | collective |
|---|---|---|---|---|
| `HyperScience` → ABBYY | **0.00** | **0.03 ✗** | **0.10 ✗** | **✓** |
| `KKR` → Kohlberg Kravis Roberts | **0.23** | **0.22 ✗** | **0.22 ✗** | **✓** |
| `Abbyy` → ABBYY | 0.20 | 0.98 ✓ | 0.30 ✗ | ✓ |
| `Five9`, `Western Digital`, full names | 0.6–1.0 | ✓ | ✓/✗ | ✓ |

Linked to the correct account: embedding-only **5/7**, pairwise **4/7**, **collective 7/7**.

Two cases need **collective *propagation***, not just relational features: `HyperScience` (a real
alias with zero string overlap) and `KKR` (an acronym a real semantic embedder still misses at
threshold, 0.22). Both are invisible to embeddings **and** to pairwise relational scoring — no
shared neighbor exists until the prose people resolve to the structured contacts first. They
appear only after propagation merges those people: the synthetic Wayne/Gotham capability,
demonstrated on real People.ai data. (Collective also beats pairwise on `Abbyy` for the same
reason — 3 of 7 forms needed the two-hop.)

## Honest caveats

- **Baseline is real and fair** — OpenAI `text-embedding-3-small`. (An earlier run used an offline
  stub and scored embedding-only at F1 0.50 / 1-of-6 variant links; the real embedder fairly raised
  it to 0.55 / 5-of-6. The collision result was identical both ways — it's structural.)
- **Lift is from relational features, not propagation.** `pairwise` and `collective` scored
  identically (1.00) — the shared contacts are direct neighbors, so collective *propagation* added
  nothing beyond pairwise-relational here (no two-hop cases like the synthetic Wayne/Gotham). What
  is validated on real data is "relationships + anchors ≫ strings/embeddings"; propagation is
  validated separately on the synthetic set and awaits a denser real graph to stress.
- **Company variants are injected** (attached to real contacts); the person-collision,
  shared-partner, and cross-source alias/acronym cases are 100% real. Data is a People.ai **demo
  org**, 10 accounts — realistic in shape, synthetic in origin.
- **Scaling note:** same-name collisions (10) didn't grow with more accounts — the new accounts had
  unique contact names — so the collision result is 10/10 at both 6 and 10 accounts. The
  cross-source propagation cases (2) and variant links (10) did scale with the added accounts/prose.

## So what

The wedge's premise survives contact with real CRM data against a strong semantic baseline: the
one failure mode that sinks embedding/name dedup and *cannot* be fixed by a better embedder —
same-name / different-entity — is exactly where relationships + anchors win, cleanly (10/10).
Abbreviations/rebrands are a real but embedder-solvable problem; same-name disambiguation is not.
Recommended next: (1) find a corpus where calls/emails and a CRM genuinely overlap, to validate
cross-source linking and stress collective propagation (this dataset didn't); (2) scale past ~6
accounts; (3) take these numbers to design partners.
