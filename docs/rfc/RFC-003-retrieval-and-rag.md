# RFC-003: Retrieval and RAG strategy

**Status:** ACCEPTED 2026-06-13
**Author:** Neha (with Claude)
**Created:** 2026-06-13
**Last updated:** 2026-06-27 (amended for ADR-007 quote-first; ADR-008 retrieval-side dedup; 2026-06-25 model/voice/follow-up updates; 2026-06-27 hybrid retrieval)

## Summary

Defines how Phase 2 turns a user question into a cited answer: chunking, embedding, vector index, retrieval, and generation. Locks in Claude Sonnet 4.6 as the LLM, BGE-M3 as the multilingual embedding model, Chroma as the local vector store, paragraph-boundary chunking at ~500 tokens, and a moderate-honesty prompt strategy. Mode-aware retrieval differs across Q&A, Pravachan, and Simple Reading.

## Motivation

The corpus is structured (RFC-002). The chat interface is being designed (RFC-004). The piece in between — how a question becomes an answer — needs a clear contract. Without RFC-003, we'd improvise during the chat-UI build phase and likely re-write retrieval mid-implementation.

## Goals

- Define the data path: `text.md` files → chunks → embeddings → vector index.
- Define the query path: user question → embed → retrieve → rerank (if any) → generate.
- Specify model choices with cost estimates pinned.
- Specify mode-aware behavior (Q&A vs Pravachan vs Simple Reading need different retrieval).
- Specify the honesty contract — when does the chat say "I don't see this in the corpus"?
- Specify citation format with chunk-level traceability.

## Non-goals

- UI rendering of citations (RFC-004).
- Multilingual prompting details (RFC-005 covers Marathi-specific generation patterns).
- Production deployment infrastructure (RFC-007).

## Architecture

```
Source files (text.md with frontmatter)
        │
        ▼
   [Chunker]  ───────────────────► chunks.jsonl (text + metadata per chunk)
        │
        ▼
[Embedder: BGE-M3]  ──────────────► embeddings/<chunk-id>.npy
        │
        ▼
 [Vector index: Chroma]  ─────────► local persistent index

User question (EN or MR)
        │
        ▼
[Language detect]
        │
        ▼
[Embedder: BGE-M3]
        │
        ▼
[Retrieve top-k from Chroma]  ◄── optional metadata filter (mode-aware)
        │
        ▼
[Optional rerank (Pravachan mode only for v1)]
        │
        ▼
[Prompt assembly: system + retrieved chunks + question]
        │
        ▼
[Claude Sonnet 4.6 API]  ─────► answer + structured citations
        │
        ▼
   Render in chat UI
```

## Component decisions

### LLM: Claude Sonnet 4.6

Decided 2026-06-13 (default). All three modes route to the same model in v1. If Pravachan quality is insufficient during polish, route Pravachan to Opus 4.7 (one-line change in code). Estimated cost: ~$33/mo for 500 devotees × 2 Q/month with prompt caching enabled.

**Update (2026-06-25):** Pravachan was briefly routed to Opus for quality exploration (F6 diagnosis), but this caused 7 000-token generation to take noticeably longer than Q&A. Pravachan is now back on Sonnet for all modes — latency parity was judged more important than the marginal quality gain at this scale. See commit `5f0a851`.

### Embeddings: BGE-M3 (multilingual, open-source, runs locally)

Why: free at inference, handles Marathi + English well, 1024-dim vectors are manageable, well-supported in Python via `sentence-transformers`. Runs on CPU acceptably for a corpus this size.

Alternatives considered:
- **Voyage 3 multilingual** (paid, slightly higher Marathi quality). Rejected: adds another vendor, ~$0.06/M tokens for embeddings (~$5/mo at our scale — small but unnecessary).
- **OpenAI text-embedding-3-large** (paid). Rejected: weak on Indic languages relative to BGE-M3.
- **multilingual-e5-large**. Comparable to BGE-M3; pick was BGE-M3 for marginally better Indic benchmark scores.

### Vector store: numpy in-memory (v1) → Chroma if/when scale demands (later)

**v1 (decided 2026-06-14):** plain numpy. Embeddings stored as `04_processed/embeddings/embeddings.npy` (float32, normalized, shape `(N, 1024)`), metadata in a parallel JSONL. At query time: load both into memory once, compute `query_vec @ embeddings.T` for cosine similarity (vectorized; ~10ms for 10K vectors on CPU), `argpartition` for top-K. Zero external dependencies, no infrastructure.

**Why this is enough for the demo:** ~7K chunks total. Even at 100K chunks the numpy approach stays under 100ms per query. Chroma's real value (metadata filtering at the DB level, sharding, fast incremental updates) doesn't apply at this scale.

**When to revisit:** if the corpus grows past 100K chunks, or if we need filtering by metadata at the vector-store level (e.g. "only chunks where work_type=book"), or if we move to a hosted backend that requires a managed vector DB.

Alternatives considered:
- **Chroma** (original plan) — local persistent. Rejected for v1 because: Python 3.8 in our anaconda env + Rust build deps caused install failures; complexity not justified at our scale.
- **FAISS** — faster than numpy at scale but no built-in metadata layer. Reconsider if numpy approach gets slow.
- **pgvector** (Postgres extension). Production-grade but adds DB requirement. Reconsider at deployment time.
- **Qdrant** — solid but adds infra. Hold for v2 if we need filter-heavy queries at scale.

### Chunking: ~500 tokens, paragraph boundaries, frontmatter metadata propagated

- **Size:** target 500 tokens per chunk; allow up to 700 if a paragraph is too long to split cleanly.
- **Boundaries:** never split mid-paragraph. Prefer section-heading boundaries.
- **Overlap:** 50-token overlap between adjacent chunks (preserves context across boundary).
- **Metadata per chunk:** from the source file's frontmatter — author, work_slug, language, page/section, lineage member, work_type (canonical/athvani/biography), variant_id (if athvani). Each chunk knows its full provenance for citation.
- **Marathi verses + meanings:** keep verse + its अर्थ (meaning) in the same chunk even if it exceeds 500 tokens. Splitting them destroys retrieval relevance.
- **Athvani variants:** chunked separately per variant file. Consolidated.md is also chunked (separately).

### Retrieval

Mode-aware behavior:

| Mode | Top-k initial | Metadata filter | Rerank | Per-source cap | Notes |
|---|---|---|---|---|---|
| Q&A | 25 → trim to 8–10 | None by default; auto-detect "about_<member>" intent in question and filter if matched | **MMR diversity (always)** + optional cross-encoder | **Max 2 per source_work_id** | Dedup is automatic — see §Deduplication layers below |
| Pravachan | 40 → trim to 15–20 across (canonical_anchor=6, athvani=8–10, biography=4) | `about_member` or theme filter if question carries hint | **MMR diversity + cross-encoder** | Max 3 per source_work_id for athvani; max 1 for canonical | Returns 3–5 chunks per output section in the structured response |
| Simple Reading | 0 at start (no retrieval); 10 only when user asks an inline question | Filtered to the current work being read | No | Not needed (single work scope) | Reading-mode questions are mostly about the chunk being read |

### Deduplication layers (per ADR-008)

Story aggregation was dropped in favor of retrieval-side dedup. Three layers run automatically:

1. **MMR diversity rerank** (post-vector-retrieval, pre-generation). After top-K vector retrieval, compute pairwise cosine similarity between candidates. Drop any chunk whose similarity to a higher-ranked chunk exceeds a threshold (start at 0.85, tune during polish). Eliminates near-duplicate narrators retelling the same incident.

2. **Per-source cap** (during MMR rerank). Limit the number of chunks per `source_work_id` in the final result (see per-mode caps in the table above). Prevents one verbose source from dominating an answer; ensures retrieval diversity across distinct compilations.

3. **Generation-side disclosure** (in the system prompt). When the LLM sees that multiple retrieved chunks share strong content overlap, it quotes the most distinctive one and adds a disclosure line: *"Similar tellings of this incident also appear in [source A], [source B]."* This turns dedup into a natural-language acknowledgment rather than hiding the redundancy.

The combined effect: a question that touches a frequently-retold incident yields one canonical-feeling quoted passage, with attribution noting that other narrators corroborate. Identical to what story aggregation would have produced, without manual curation.

### Generation

Each mode has its own system prompt template:

**Q&A** — quote-first curation pattern (per ADR-007). System prompt enforces:
- Select 2–5 retrieved passages that *directly* address the question.
- Present each passage **verbatim**, indented as a blockquote, with source attribution on the line below.
- Write **minimal connective tissue**: a short framing sentence at the start, optional brief context between quotes, and optionally a 1–2 sentence synthesis at the end. When passages speak for themselves, the model stays out of the way.
- The quote IS the citation — no separate `[#N]` markers in the body. Attribution is rendered directly under each quote.
- If the corpus doesn't have quotable passages on the topic, say "the corpus doesn't directly address this" — moderate honesty, and naturally enforced (no quotable text → nothing to fabricate).
- Match the user's language. If the question is Marathi and best sources are English, quote English verbatim and offer a Marathi paraphrase below the quote (clearly distinguished).
- Distinguish *canonical teaching* (from `01_canonical/`) from *oral recollection* (from `02_aggregated/athvani/`) via a source-type label in the attribution line: e.g., `— Pathway to God in Hindi Literature, ch. 4 (canonical)` or `— निंबाळचे जुने घर (athvani, narrator: Vijaya Apte)`.

**Update (2026-06-25): answer shape.** Doctrinal Q&A answers now have an explicit **intro paragraph** before the citations and a **concluding paragraph** after them (rounding out the structure). This was added to make answers feel complete rather than list-like. The retrieval breadth rule is: **at most one passage per source work** in the final answer (prevents one verbose source from dominating); implemented via per-source cap + survey-the-literature prompt instruction. See commit `f96612e` (citation breadth) and `19d0feb` (intro/conclusion).

**Update (2026-06-25): voice/persona.** All three system prompts now carry a **VOICE/PERSONA section** instructing the assistant to be warm, deeply respectful, and eager to share insight from the literature — while keeping verbatim quotes strictly verbatim and avoiding turning answers into effusive praise. See commit `cf2ff0d` and ADR-006 (warm-devotional aesthetic).

**Update (2026-06-25): conversational follow-ups.** Q&A follow-up questions now carry the **full conversation history** (prior turns) and the system prompt instructs the model not to repeat passages already cited. The `AskRequest.history` field (previously annotated "not used") is live. See ADR-014 and commit `020647e`.

**Pravachan** — structured outline:
```
## Thesis
<1-2 sentences>

## Canonical anchor
<1 passage from canonical with citation>

## Supporting athvani
1. <athvani sketch with citation>
2. <...>
3. <...>
(3-5 total)

## Suggested sequence
<outline for how to deliver this pravachan>
```

**Simple Reading** — initial output is the chosen text rendered paragraph-by-paragraph with bookmark state stored. Inline questions during reading use the Q&A prompt with a metadata filter restricting to the current work.

### Honesty contract (moderate stance, per Q2)

In every system prompt, include:

> "You are answering questions about the literature of the Nimbal sampradaya. If the retrieved sources support an answer, give it with citations. If sources only partially support an answer, give the answer that's supported and explicitly flag what's missing: 'The corpus addresses A and B, though it doesn't directly mention C.' If sources are too thin to answer at all, say 'The corpus doesn't directly address this — here's what it does say nearby.' Never invent details, dates, or quotations. When the question is about lineage, be precise about who taught whom."

### Citation format (per ADR-007)

In the generated answer (quote-first):

```
Here's what the corpus contains on this:

> "Bhakti is at once the means and the end of mysticism. It is by bhakti that
> the soul approaches God, and it is in bhakti that the soul finds its fulfilment."
> — Pathway to God in Hindi Literature, ch. 4, p. 87 (canonical)

> "Among the Marathi sants, Jnaneshwar, Tukaram, Eknath, and Ramdas embody
> the bhakti path in its lived form."
> — Mysticism in Maharashtra, preface (canonical)

These passages together describe bhakti as both the path and its culmination.
```

The quote itself is the citation surface. The attribution line directly under each quote contains: source work, chapter/page, source-type label (canonical / athvani / biography / periodical / reference), and for athvani: the narrator. Clicking the attribution opens the source preview (RFC-004 handles rendering).

### Prompt caching

Use Anthropic prompt caching for the system prompt + the per-mode template. Cached portion is ~80–90% of input tokens; remaining is the question + retrieved chunks. Expected effective input cost: 10–20% of nominal.

## Tradeoffs

- **BGE-M3 vs paid embeddings.** Saves cost, possibly slight quality drop in edge cases. Re-evaluate after polish week.
- **Chroma vs production-grade pgvector.** Chroma is local — fine for v1 demo, but production will likely need pgvector. Migration is straightforward (Chroma exports → re-index in pgvector).
- **No rerank in Q&A mode.** Simpler. Rerank can be added if Q&A quality is weak during polish.
- **Single LLM for all modes.** Simpler routing, easier to tune. Risk: if Pravachan synthesis is weak on Sonnet, we'll either route to Opus or simplify the Pravachan prompt.
- **Moderate honesty.** Will the chat sometimes appear to "hedge"? Possibly. The polish phase tunes the prompt to keep hedging minimal.

## Open questions

| # | Question | Resolve in |
|---|---|---|
| OQ-1 | Should chunks include adjacent chunk ids as "neighbors" for the LLM to grow context if needed? | Polish phase if early evals show context-too-narrow |
| OQ-2 | Reranker for Pravachan — MMR (cheap) or a cross-encoder like `bge-reranker-v2-m3` (better but adds latency)? | RFC-003-amendment after first Pravachan evals |
| OQ-3 | Should the system prompt list a few canonical works by title so the LLM knows the lineage scope, or stay corpus-agnostic? | Polish phase |
| OQ-4 | Cache invalidation when corpus updates — full rebuild or incremental? | Tooling decision; defer to ingestion script (#7) |

## References

- [PRD.md §4 Phase 2](../PRD.md)
- [RFC-001 §Scope, §Demo flow](RFC-001-demo-mvp.md)
- [RFC-002 §6 meta.yaml schemas](RFC-002-corpus-structure.md) — frontmatter is the citation backbone
- ADR-003 (Anthropic API)
- ADR-004 (Bilingual from day 1)
- BGE-M3 model: https://huggingface.co/BAAI/bge-m3
- Chroma: https://www.trychroma.com/
- Anthropic prompt caching docs

## Amendment (2026-06-27): Hybrid retrieval — BM25 + Reciprocal Rank Fusion

Dense-only retrieval missed keyword-specific queries where the relevant passage
uses the query's distinctive term only in contrast (e.g. "Bhakti does not
consist … in formal idol-worships" scored cosine rank 34 for "idol worship").
The 1-per-work MMR cap then excluded it in favour of higher-scoring general-devotion chunks.

The retrieval pipeline now fuses dense cosine scores with **BM25 lexical
scores** via **Reciprocal Rank Fusion (RRF)** before candidate selection. A
`BM25Index` is built lazily over all corpus chunks at startup and cached
in-process; `rrf_fuse(dense_ranks, lexical_ranks, k=60)` produces the fused
score array; `fused_candidate_scores()` is the single helper used by all four
call sites (`server._retrieve`, `chat.run_retrieval`, `tune_sweep`,
`rank_probe`). Intent-tier weights (RFC-011) are applied to the dense scores
before fusion.

**Critical constraint:** MMR must rank on the **fused** score, not the raw
dense score. A lexically-surfaced chunk entering the candidate pool with a low
raw-dense score would be dropped by the 1-per-work cap under MMR, making hybrid
retrieval a no-op. This was a real bug (commit `80e2b2d`) fixed at all four
call sites. See [ADR-015](../decisions/ADR-015-hybrid-retrieval-bm25-rrf.md)
for the full design, alternative analysis, and commit references.
