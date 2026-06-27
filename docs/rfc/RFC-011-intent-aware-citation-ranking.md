# RFC-011: Intent-aware citation ranking

**Status:** ACCEPTED 2026-06-24
**Author:** Neha (with Claude)
**Created:** 2026-06-23
**Last updated:** 2026-06-27

## Picks confirmed (2026-06-23 discussion)

- **Scope:** both a general source-authority tier *and* explicit near-duplicate
  demotion (canonical original beats its secondary reprint).
- **Intent-conditioned:** tier weighting depends on the **query's intent** — a
  philosophical question weights canonical up; an "athvani" question weights
  recollections up.
- **Intent detection:** hybrid — a multilingual heuristic decides when
  confident, a cheap LLM (Haiku) classifies only ambiguous queries.
- **Athvani are evidence for doctrine:** for a doctrinal query, recollections
  get a *slight boost* (the gurus' lived examples illustrate the philosophy),
  not a demotion.
- **Tiers clubbed:** athvani + biography collapse into one *recollections* tier;
  "anecdotal" and "biographical" intents collapse into one *narrative* intent.
- **Soft, not hard:** weights tilt cosine relevance; they do not hard-filter. A
  strongly-relevant recollection can still surface for a philosophical question,
  just demoted.
- **Approach A** (extend the current additive boost pipeline) over a dedicated
  rerank stage (B) or a probabilistic intent distribution (C).

## Summary

Make citation ranking **intent-aware**. Today retrieval is cosine score plus a
single flat `+0.07` boost for canonical works by lineage-master authors, then
MMR. This RFC replaces the flat boost with a per-tier weight **conditioned on
the query's intent**, and adds **authority-aware near-duplicate demotion** so a
canonical original is preferred over a secondary source that reprints it. Intent
is detected by a multilingual heuristic with a cheap LLM fallback for ambiguous
queries.

## Motivation

A doctrinal Q&A ("quote the passages on self-surrender") cited the badly-OCR'd
**"ACPR Silver Jubilee Souvenir"** (`kind=biography`, `02_aggregated`, English)
even though a **clean** copy of the same Gita passage exists in the canonical
**"Bhagavadgita as Pathway to God Realization"** (`kind=canonical`,
`author=gurudev_ranade`, `01_canonical`). Two problems combined:

1. **Authority:** a secondary reprint outranked the canonical original. The
   souvenir's English text matches an English query about as well as the
   canonical book's, and the flat `+0.07` (RFC-003) was not enough to keep the
   souvenir out of the top-k or out of the model's hands.
2. **Intent-independence:** the boost is the same regardless of what the user
   asked. But the *right* source depends on the question. A philosophical
   question wants the masters' own teaching; an "athvani about Maharaj" question
   wants exactly the recollections we would otherwise demote.

So a static boost is the wrong shape. The correct ranking is **cosine
relevance, tilted by source authority, where authority is a function of query
intent** — plus a guard so duplicated content always resolves to the
higher-authority copy.

## Goals & non-goals

**Goals**
- Rank canonical works above secondary recollections for doctrinal/philosophical
  questions, and the reverse for narrative ("athvani"/biographical) questions.
- For doctrinal questions, give recollections a *slight* positive weight (lived
  examples support doctrine) — not a demotion.
- When two retrieved chunks are near-duplicates, surface only the one the active
  intent ranks higher (resolves the souvenir-reprints-canonical case).
- Detect intent cheaply: no extra API call on the common (heuristic-confident)
  path; a single cheap LLM call only when ambiguous.
- Keep weights soft (tilt, not filter) and the magnitudes in one tunable place.

**Non-goals**
- Not fixing source data quality (OCR garbage in the souvenir) — see
  RFC-009 / the ongoing re-OCR. Ranking only decides *order*.
- Not mode-specific priors (e.g. Pravachan inherently leaning narrative) — intent
  is query-driven in v1; mode priors can come later.
- Not a learned/ML reranker. Hand-tuned additive weights, swept offline.
- Not changing the embedding model, chunking, or the MMR diversity mechanic
  itself (only adding a duplicate-skip to it).

## Proposed design

### Data flow

```
query
 → classify_intent(query)                              # NEW
 → embed query → cosine scores
 → apply_intent_tier_weights(scores, metas, intent)    # REPLACES apply_primary_tier_boost
 → mmr_rerank(..., skip near-duplicates of higher-ranked chunks)
 → top-k chunks
```

The three call sites that retrieve (`server._retrieve`, `chat.run_retrieval`,
`tune_sweep`) classify intent once per query and thread it into the weighting
and rerank steps.

### Intents and source tiers

**Intents:** `doctrinal` · `narrative` · `navigational` · `unknown` (default).

**Source tiers** (`chunk_tier(meta)`), derived from `kind` / `source_path`:

| Tier | Membership |
|---|---|
| `canonical` | `kind=canonical` (`01_canonical`) |
| `recollections` | `kind ∈ {athvani, biography}` (`00_raw`, `02_aggregated`) |
| `reference` | `kind=reference` (`03_catalog`) |

Orthogonal: a **primary-author bonus** for canonical works by lineage masters
(`PRIMARY_AUTHORS`), preserving today's preference for the masters' own writing
over other canonical authors.

### Intent × tier weights (added to cosine, before MMR)

| Intent | canonical | recollections | reference |
|---|---|---|---|
| `doctrinal` | +0.10 | +0.04 | −0.12 |
| `narrative` | 0 | +0.10 | −0.08 |
| `navigational` | 0 | 0 | +0.08 |
| `unknown` | +0.05 | 0 | −0.08 |

Plus **primary-author bonus +0.04** on canonical lineage-author chunks. So on a
doctrinal query: canonical-primary = +0.14, canonical-other = +0.10,
recollections = +0.04, reference = −0.12. (Cosine top scores today ≈ 0.5–0.7, so
these deltas meaningfully reorder near-ties without swamping a genuinely strong
match — the soft-tilt requirement.)

These magnitudes and `DUP_THRESHOLD` (below) are **starting values** in one
constants block, swept by `tune_sweep.py`. The matrix *structure* is the
deliverable; the numbers are tuned.

### Intent classification (`tools/intent.py`)

`classify_intent(query) -> Intent`:

1. **Heuristic (free, common path).** Multilingual cue lexicons per intent
   (EN + MR), e.g.
   - doctrinal: `teaching, philosophy, meaning, doctrine, concept, शिकवण, तत्त्वज्ञान, अर्थ`
   - narrative: `athvani, story, incident, memory, anecdote, आठवण, प्रसंग, गोष्ट`
   - navigational: `which works, list, index, what books, structure, कोणते ग्रंथ`

   Score each intent by cue hits. A clear single winner → return it.
2. **LLM fallback (ambiguous only).** No/conflicting cues → one cheap **Haiku**
   classification returning a single label. Result cached per query string.
3. **Failure → `unknown`.** Any API error/timeout, or fallback disabled →
   `unknown` (mild canonical preference ≈ today's behavior). Intent classification
   never blocks retrieval.

### Authority-aware near-duplicate demotion (in `mmr_rerank`)

MMR already penalizes a candidate by its max similarity to already-selected
chunks (diversity). Extend it: when a candidate's cosine similarity to an
already-selected chunk ≥ `DUP_THRESHOLD` (start 0.92), **skip the candidate
entirely**. Because the intent weighting makes the higher-authority copy score
higher, it is selected first; its near-duplicate (e.g. the souvenir reprint) is
then skipped rather than taking a second slot. No separate dedup pass needed.

### Components touched

- `tools/intent.py` (new): `classify_intent`, lexicons, Haiku fallback, cache.
- `tools/retrieve.py`: add `chunk_tier`; replace `apply_primary_tier_boost` with
  `apply_intent_tier_weights(scores, metas, intent)`; extend `mmr_rerank` with the
  duplicate-skip; constants block for the matrix + `DUP_THRESHOLD`.
- `tools/server.py`, `tools/chat.py`, `tools/tune_sweep.py`: classify intent per
  query and pass it through.

### Error handling

- Heuristic always returns (confident label or "ambiguous" → triggers fallback).
- Haiku fallback failure → `unknown`; cached per query to avoid repeat cost.
- If `intent.py` is unavailable, retrieval defaults to `unknown` weighting
  (≈ current behavior). Retrieval is never blocked on classification.

### Testing

- **Unit (no API):** heuristic on representative EN/MR queries → expected intent;
  `apply_intent_tier_weights` produces the expected per-tier deltas;
  `chunk_tier` maps each `kind`; duplicate-skip drops the near-dup on synthetic
  embeddings.
- **Integration (cost-aware, run manually):** the self-surrender question cites
  the canonical Gita over the souvenir; an "athvani about…" query surfaces
  athvani/recollections; the Haiku fallback fires only on ambiguous queries.

## Alternatives considered

- **B — Dedicated rerank scoring stage.** A new reranker computing one explicit
  composite (`cosine + intentTierWeight + primaryBonus − dupPenalty`) with all
  weights named in one place, MMR diversity folded in. Cleaner separation and
  more extensible (quality/recency later), but a larger refactor of `retrieve.py`
  for no behavioral gain over A today. Revisit if scoring factors multiply.
- **C — Probabilistic intent (distribution over intents).** Tier weight =
  expected weight over a soft intent distribution; smoother on ambiguous queries.
  But the hybrid classifier's LLM fallback already handles ambiguity, and a
  distribution is harder to reason about and tune. Overkill for v1.
- **Hard tier filter / strict tier ordering.** Sort by tier first, cosine
  second (or drop low tiers outright). Rejected: a barely-relevant canonical
  chunk would beat a strongly-relevant recollection, and it breaks narrative
  queries. The requirement is a soft tilt.

## Tradeoffs & risks

- **Weight tuning.** Additive deltas must be calibrated to the cosine scale;
  too large over-promotes weak-but-canonical chunks, too small under-fixes the
  souvenir case. Mitigation: one constants block + `tune_sweep.py`, soft by design.
- **Heuristic brittleness.** Cue lexicons miss unusual phrasings; mitigated by
  the LLM fallback and the safe `unknown` default.
- **Fallback cost/latency.** A Haiku call on ambiguous queries adds ~1–2s + a
  small cost; bounded by caching and the heuristic handling the common path.
- **Misclassified intent** weights the wrong tier — but softly, and a strong
  cosine match still surfaces. Worst case ≈ today's intent-independent behavior.
- **`DUP_THRESHOLD` sensitivity.** Too low could drop legitimately distinct
  chunks; tuned on real near-duplicate pairs (souvenir vs canonical).

## Open questions

- Exact cue lexicons (EN + MR) — seed list to expand against real queries.
- Final weight magnitudes and `DUP_THRESHOLD` — set by an offline sweep.
- Whether `navigational` should also adjust the existing ADR-010 doctrinal/meta
  prompt path, or remain purely a retrieval-tier signal.
- Whether to add mode priors (Pravachan → narrative-leaning) in a later revision.

## References

- [RFC-003 Retrieval & RAG strategy](RFC-003-retrieval-and-rag.md) — the pipeline
  this amends (`PRIMARY_TIER_BOOST`, MMR, per-source cap).
- [ADR-010 Q&A doctrinal-vs-meta classification](../decisions/ADR-010-qa-doctrinal-vs-meta-classification.md)
  — related answer-time intent signal (post-retrieval).
- [ADR-011 Structured-output contract](../decisions/ADR-011-structured-output-contract.md)
  — citation shape consumed downstream (reference-and-splice amendment).
- `tools/retrieve.py`, `tools/server.py`, `tools/chat.py`, `tools/tune_sweep.py`
  — implementation sites.
