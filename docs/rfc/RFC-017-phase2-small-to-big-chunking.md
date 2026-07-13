# RFC-017: Phase 2 — small-to-big (parent–child) chunking + arthasahit citable-span

**Status:** ACCEPTED 2026-07-13 (implementation deferred — build before public launch)
**Author:** Neha (with Claude)
**Created:** 2026-07-13

## Summary

Re-chunk the corpus with a **parent–child (small-to-big)** scheme: retrieve on **small
children** (one sentence, or one abhang/ovi for verse works) for precise recall, but answer
from the **big parent** (the ~500-token section) for context. This fixes the recall-
granularity failure where a specific sentence buried in a large mixed chunk gets a low
whole-chunk cosine and never surfaces (the "lightning struck Gurudev's house" miss). The
same chunker change **subsumes the arthasahit retrieve-vs-cite work (task #35)**: a verse
child embeds `verse + meaning` (recall) but carries a `cite_text = verse only` so a sadhak's
meaning is never cited as Gurudev's words. Implements RFC-014 Phase 2.

## Motivation

- **Recall granularity.** Diagnosed live (docs + dual-retrieval work): "निंबाळच्या घरावर वीज
  पडली" sits as one sentence inside a big multi-topic athvani chunk, so its whole-chunk
  cosine is low and it ranks ~2300th; no fusion/cap/window tuning surfaces it (ADR-017 notes
  this is the residual dual-retrieval can't fix). Only finer chunks fix it.
- **Arthasahit attribution.** The 7 held "अर्थासहित" books (memory: arthasahit-retrieve-vs-cite)
  pair Gurudev's verse selection with a *sadhak-authored* meaning; we must embed the meaning
  for recall but cite only the verse. A per-child `cite_text` makes this a natural special
  case rather than a bespoke pipeline.

## Goals

- A buried sentence/verse is retrievable as its own unit.
- The answer model still sees full surrounding context (the parent section).
- Citations remain precise (the child) and correctly attributed (`cite_text`).
- One coherent chunker change covers both small-to-big and the arthasahit split — one
  re-embed, not two.
- Read-in-full, splice, grounding/enforce, and dual-retrieval all keep working.

## Non-goals

- Retrieval fusion changes (dual-retrieval / ADR-017 stays as-is; it operates over children).
- Re-OCR of garbled scans (Phase 3).
- Hosting (RFC-016) — separate, sequenced after this.

## Proposed design

### Parent–child model

`tools/chunker.py` emits two linked levels:

- **Parent** — the existing ~500-token, paragraph-grouped section chunk. The *context* unit
  handed to the answer model. Kept ≈ as today.
- **Child** — one sentence (prose) or one abhang/ovi (verse). The *retrieval* unit. Every
  child links to its parent.

Embeddings + BM25 index are built on **children only**. Parents are stored for context
lookup (a `kind:"parent"` row in `chunks.jsonl`, excluded from the embedding set, or a
sidecar `parents.jsonl` keyed by `parent_id`).

### Child schema (chunks.jsonl)

Each child row adds to the current metadata:

| field | meaning |
|---|---|
| `parent_id` | the parent section this child belongs to |
| `text` | the child's own sentence/verse |
| `embed_text` | what gets embedded: the sentence **+ a small neighbor window** (± ~1 sentence) so short units still carry signal. Falls back to `text` when the window adds nothing. |
| `cite_text` | the verbatim span allowed in a citation. `= text` for normal works; `= verse only` for arthasahit; **absent ⇒ retrieval-only (never citable)**. |

`embed_text` drives the vector; `cite_text` drives splice/quoting; `text` is the raw child.

### Arthasahit split (subsumes #35)

For the 7 books, the chunker parses each entry into `verse` + `meaning`:

- child = the **verse**; `embed_text` = `verse + meaning` (meaning, esp. the English gloss,
  boosts recall); `cite_text` = **verse only**.
- The verse↔meaning boundary is **not uniform** (the `अर्थ` marker ranges 51–881 per book;
  some sections are TOC/index). Strategy: split confidently on the strongest available signal
  per book (`अर्थ -` marker, then numbered-meaning lines, then an English gloss in parens);
  **where the split is uncertain, emit the child with NO `cite_text`** (retrieval-only). This
  guarantees we never mis-cite a meaning; the cost is some verses being non-citable until the
  originals arrive (approach b).

### Retrieval (expand children → parents)

`tools/server.py::_retrieve` keeps dense + BM25 + dual-RRF (ADR-017), now over children.
After ranking, **expand**: group the top children by `parent_id`, dedupe, cap per parent,
and load parent text. The answer model receives the **parent sections** (context) with the
matched child(ren) flagged as the precise anchor(s) to quote. `max_per_source` becomes
`max_per_parent`. Candidate pool widens (more, smaller units) — tune `INITIAL_CANDIDATES`.

### Grounding, splice, Read-in-full

- **Splice / quote-by-reference**: anchor on `cite_text` (not the whole child) so an
  arthasahit citation copies only the verse.
- **Enforce / verify_citations**: unchanged — still checks that cited spans exist in the
  provided passages (now `cite_text`).
- **Read-in-full / readPage**: point the body-match at the **parent** section text; the
  existing `reading_page_for_body` logic maps it to the reading page.

### Re-embed (one-time, GPU cloud)

Sentence children ≈ **60–100k** (vs 16,888). Every child_id is new ⇒ a **full** re-embed.
Run once on a **rented GPU instance** (BGE-M3, ~1–3 h, ~$3–15), download `embeddings.npy` +
`chunks_meta.jsonl`, verify row-alignment, commit the index artifacts. (Aligns with the move
to hosting, RFC-016.) After this, the chunk_id-keyed incremental path (ADR-012) resumes for
future batches.

### Eval

Extend `tools/eval_retrieval.py` gold cases with: the lightning incident (must now surface
its child in top-k), 3–5 other "specific sentence inside a big section" cases, and the
existing doctrinal cases (must not regress). Add an arthasahit case asserting the cited span
is the verse, never the meaning. Check retrieval latency (larger BM25 index + more candidates).

## Alternatives considered

- **Semantic-boundary chunks** — better boundaries, no parent plumbing, but a long topical
  section is still one chunk, so a buried sentence can still hide. Rejected: doesn't fully fix
  the presenting problem.
- **Smaller fixed chunks (~250 tok)** — trivial, but boundaries still cut mid-thought and the
  answer model loses context. Rejected.
- **Arthasahit as a bespoke pipeline** (separate from Phase 2) — would mean two chunker passes
  and two re-embeds. Folding it into the child schema (`cite_text`) is strictly cheaper.

## Tradeoffs & risks

1. **Re-embed cost & the index grows** — ~4–6× more vectors; `embeddings.npy` and the BM25
   index grow accordingly (RAM on the host, RFC-016). Acceptable; still well within a 3–4 GB
   backend.
2. **Single-sentence embeddings are noisier** — mitigated by the `embed_text` neighbor window.
3. **Parent lookup adds a step** — one extra load per distinct parent per query; cache parents
   in RAM (they're the section chunks).
4. **Arthasahit parse imperfect** — the conservative "uncertain ⇒ retrieval-only" rule trades
   coverage for never mis-citing; revisit when Gurudev's original vachanamrut arrive (approach b).

## Open questions

1. Neighbor-window size for `embed_text` (±1 sentence vs ±2) — tune on the gold set.
2. Parent storage: inline `kind:"parent"` rows vs a `parents.jsonl` sidecar — pick during
   implementation for the simplest chunker/embedder change.
3. Whether to flag-gate the new retrieval path (`ENABLE_SMALL_TO_BIG`) for an A/B against the
   current index before the full cutover.

## References

- RFC-014 (retrieval/grounding re-arch — defines Phase 2), ADR-012 (chunk_id carry-over),
  ADR-017 (dual-retrieval), ADR-015 (hybrid BM25+RRF)
- memory: `arthasahit-retrieve-vs-cite` (the #35 decision this subsumes)
- `tools/chunker.py`, `tools/embedder.py`, `tools/server.py` `_retrieve`, `tools/schemas.py`
  (splice), `tools/eval_retrieval.py`
