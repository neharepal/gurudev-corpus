# Corpus Quality Remediation Plan — 2026-07-08

**Context:** A live demo surfaced poor answer quality: expected passages not
retrieved, Marathi questions handled poorly, a wrong book title, and a suspicion
that source material was never ingested. Three parallel investigations confirmed
**three independent root-cause areas**. This plan sequences the fixes.

**Evidence sources:** ingestion audit + `docs/corpus-coverage-audit-2026-06-17.md`;
retrieval trace of `tools/retrieve.py` / `tools/server.py` / `tools/query_translation.py`;
metadata audit of `03_catalog/catalog.yaml` + per-work `meta.yaml`/`text.md`.

**Hard constraint:** verification must NOT call `/api/ask` or any paid LLM/API
(cost limit). Retrieval quality is validated **offline** (local BGE-M3 embeddings +
a gold query set), not via live answers.

---

## Problem summary

### A. Corpus substantially under-ingested (coverage)
- Only **~30 of 175** master-list titles ingested (~17%). Measured in the
  2026-06-17 coverage audit.
- **Cause A1 — never uploaded (~130 titles, 74%):** all V.H. Date works, all
  Ramanna Kulkarni works, all letters collections, most biographies/athvani. No
  file ever arrived. *Data-sourcing gap, not a pipeline bug.*
- **Cause A2 — on disk but never triaged (~57 files / ~22–26 works):** Bhausaheb &
  Amburao athvani, the Dhyangita word-meaning commentary, the *Guru Ha Parabrahma
  Kewal* biography, `परमार्थपर व्याख्याने` vols, etc.
- The 2026-07-08 re-download (`00_raw/neha-initial-download-2026-07-08/`, 151
  files) is a complete copy of the on-disk material → **fixes A2's availability**;
  does **not** address A1.

### B. Retrieval mis-tuned (answer quality)
Confirmed causes (offline, no embeddings guesswork):
- **B1 `candidates=30`** (`retrieve.py:35`, `server.py:1234`) — only top 0.19% of
  15,781 chunks reach MMR. Highly relevant chunks are cut before ranking.
- **B2 `max_per_source=1`** for unscoped QA (`server.py:1249-1250`) — ≤8 distinct
  works per answer; two closely-related works can't both surface.
- **B3 BM25 "Gurudev's" IDF trap** (`retrieve.py:76-103`) — the rare token
  "gurudev's" (IDF 5.62) over-boosts *biography/recollection* chunks over the
  canonical doctrinal passages (which don't say "Gurudev's" in-sentence).
- **B4 lexical gap** — Gurudev's phrase is "One God, One World, One **Religion**",
  so a "…humanity" query misses it; only `pathway-to-god-in-the-vedas`
  (`other_authors`, slightly demoted) uses "humanity".
- **B5 Marathi one-directional translation** (`query_translation.py:28-34`,
  `server.py:482-484`) — only EN→MR is translated for a dual-vector. A **Marathi
  query gets no English vector**, so English passages score at (lower)
  cross-lingual cosine and BM25=0 → nearly invisible. This is the Marathi failure.

### C. Metadata errors (correctness/trust)
- **C1 (P0)** `bhagavadgita-as-pathway-to-god-realization` title is wrong →
  *"The Bhagavadgita as a Philosophy of God-Realisation"* (verified from the book's
  own title page, `text.md:18`). Fix `meta.yaml`, `text.md` front matter,
  `CORPUS_CONTENTS.md`. Work-id slug is also wrong (optional rename).
- **C2 (P1)** `vedant` → *"Vedanta: The Culmination of Indian Thought"*.
- **C3 (P1)** likely duplicate: `parmartha-sopan` (superseded) vs
  `hindi-parmarth-sopan` (clean, cataloged) — retire the former if confirmed.
- **C4 (P2)** ~10 placeholder / transliteration-only / auto-generated titles
  (`bhagvadgeeta`, `kakanchi-pravachane`, `n-g-damle-pravachan`, …).
- **C5** several on-disk works are **absent from `catalog.yaml`** (incl. the
  Bhagavadgita book) — a coverage/consistency gap in its own right.

---

## Remediation phases (proposed sequence)

Rationale: do the fast, high-impact, low-risk work first (it directly lifts demo
quality), then the heavy coverage work, with data-sourcing as a parallel track.

### Phase 0 — Metadata fixes (C) — fast, low risk
- Fix C1, C2 titles in every place a title lives: per-work `meta.yaml`
  (`title`, `title_en`), `text.md` front matter (`title_en`), `catalog.yaml`
  (when present), and `CORPUS_CONTENTS.md`.
- Investigate + retire the C3 duplicate (`parmartha-sopan`) after confirming
  `hindi-parmarth-sopan` fully supersedes it (compare chunk coverage; ensure no
  citations/URLs depend on the old id).
- Catalog the uncataloged works (C5) or, at minimum, the Bhagavadgita book.
- Decide C4 (placeholder titles) — fix now or defer.
- **Verification:** grep each old title string is gone; reader/`/read/<slug>` shows
  the corrected title; `python3 -m py_compile` / `tsc` unaffected (data only).
- **Open decision:** rename the Bhagavadgita **work-id**
  (`…-philosophy-of-god-realisation`)? Cleaner, but changes `/read/<slug>` URLs and
  any saved history/deep-links → bigger blast radius. Recommend: fix titles now,
  defer slug rename unless required.

### Phase 1 — Retrieval tuning (B) — high impact, contained
- **B1:** raise `INITIAL_CANDIDATES` 30 → 80–100 (`retrieve.py:35`, confirm
  `server.py` inheritance). Re-check latency (MMR is O(candidates²) on small vecs —
  fine at 100).
- **B2:** for unscoped QA, `max_per_source` 1 → 2 (`server.py:1249-1250`).
- **B5 (Marathi):** make translation bidirectional — when the query is Marathi,
  also compute an English translation vector and take the per-passage max (mirror
  the existing EN→MR path). Touches `query_translation.py:needs_translation` +
  `server.py:~482`.
- **B3/B4 (optional, second pass):** damp high-IDF meta-tokens ("gurudev's") for
  `kind=recollections/biography` relative to canonical, analogous to the RRF fused
  tier bonus; consider light query expansion ("humanity"↔"religion") — only if the
  eval shows B1/B2/B5 don't already recover the target passages.
- **Verification (offline, no API):** build a small **gold query set** (incl.
  "One God, One World, One Humanity" EN + its Marathi form, plus 8–10 known
  EN/MR questions with expected work_ids). Script: embed each query with the repo's
  BGE-M3 setup, run the actual `_retrieve` ranking offline, assert the expected
  work_ids appear in top_k. Reuse/extend `tools/tune_sweep.py` / `tuning/`. This is
  the acceptance test for the tuning change — no LLM calls.
- **Coordination:** these files are the RFC-011 retrieval session's territory —
  confirm it's paused, and consider an RFC-003/RFC-011 amendment noting the new
  values.

### Phase 2 — Ingest the on-disk material (A2) — heavy, high coverage gain
- Triage `00_raw/neha-initial-download-2026-07-08/` against the current corpus:
  dedupe (many overlap with existing works), classify each doc (canonical book /
  athvani / biography / lecture), following the RFC-009 pipeline.
- Extract → chunk (`tools/chunker.py`) → embed (`tools/embedder.py`, incremental)
  → update `catalog.yaml`, per-work `meta.yaml`/`text.md`, then **regenerate
  `CORPUS_CONTENTS.md`** (`tools/build_corpus_manifest.py`).
- Prioritize the highest-value missing works first: Bhausaheb & Amburao athvani,
  the Dhyangita commentary, *Guru Ha Parabrahma Kewal*, `परमार्थपर व्याख्याने` vols.
- **Verification:** manifest `complete: true`; new work_ids retrievable in the
  offline gold-query check; reader opens the new works; spot-check OCR/garble on a
  few pages.
- **Risk:** re-embedding shifts the corpus; do it as a controlled batch and
  re-run the Phase-1 gold-query check afterward (candidate cutoff matters more as
  chunk count grows).

### Phase 3 — Source the missing ~130 titles (A1) — user-led, parallel
- Not a code task: these files must be gathered (sadhak network / archives) and
  uploaded. I can produce a precise **missing-titles checklist** (from the coverage
  audit, grouped by the 11 sections) to hand to whoever collects them. As batches
  arrive, they run through Phase 2's pipeline.

---

## Open decisions (need your call)
1. **Bhagavadgita work-id rename** — rename the slug, or just fix the title? (blast
   radius: `/read/<slug>` URLs, saved history/deep-links).
2. **Placeholder titles (C4)** — fix all now, or only P0/P1?
3. **Retrieval values** — accept the proposed `candidates≈100`, `max_per_source=2`,
   and bidirectional MR as the targets, or tune to specific numbers via the sweep?
4. **Re-embed strategy** — incremental (add new chunks only) vs full rebuild.
5. **Sequence** — is Phase 0 → 1 → 2 (with 3 in parallel) the order you want?

## Notes
- Everything above is verifiable offline; no `/api/ask` needed until you choose to
  spot-check final answer quality yourself.
- Retrieval files (`retrieve.py`, `server.py`, `query_translation.py`) are shared
  with the RFC-011 session — coordinate before editing.
