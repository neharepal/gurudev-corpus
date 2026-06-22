# ADR-008: Skip story aggregation; deduplicate at retrieval and generation time

**Status:** ACCEPTED
**Date:** 2026-06-14
**Author:** Neha (with Claude)

## Context

The original Phase 1 design (per the earliest project memory and the seeded `the-old-house-at-nimbal` template) included **story aggregation** — identifying when multiple narrators told the same athvani incident and consolidating them into a single canonical story with all variants preserved underneath. The stated motivation was *deduplication of data*: so the chat wouldn't surface 5 narrations of the same incident as 5 separate answers.

In practice, after running the tuned matcher on ~30 athvani docx files, **562 candidate segments landed in the review queue requiring human editorial decisions** — "is this incident the same as that incident?" — at a scale of effort that isn't justifiable before the July 12 demo.

Reviewing the original motivation, the user noted that dedup is the *real* concern; story aggregation was just one way to achieve it. There are cheaper ways.

## Decision

**Drop story aggregation as a Phase 1 deliverable.** Solve deduplication at retrieval and generation time instead, via three layers built into the RAG pipeline:

1. **MMR diversity rerank at retrieval.** After top-K vector retrieval, run Maximum Marginal Relevance to drop chunks whose embeddings are within X% similarity of a higher-ranked chunk. Standard IR technique; eliminates near-duplicates automatically.
2. **Source-grouping cap.** Limit to N chunks per `source_work_id` in any single retrieval result. Prevents one verbose source from dominating an answer.
3. **Generation-side disclosure.** System prompt instructs the LLM: *"If multiple retrieved passages tell the same incident, quote the most distinctive one and note 'similar tellings also appear in [other sources]' below the quote."* Dedup becomes a natural-language disclosure rather than data manipulation.

These three together approximate the user-facing benefit of story aggregation (one canonical telling, acknowledgment of variants) without any manual curation.

The existing seed story `the-old-house-at-nimbal` and the four auto-created placeholder stories are removed from `02_aggregated/athvani/` and `03_catalog/story_index.yaml`. The matcher script `tools/ingest_athvani.py` is preserved but unused — it may be repurposed later for variant fingerprinting if useful.

## Alternatives considered

- **Story aggregation as originally planned.** Rejected: 562-item manual triage is too much effort for the demo, and would scale linearly with corpus size.
- **LLM-assisted clustering of the 562 items.** Considered. Useful but still requires user to review ~30 proposed clusters and would need cluster-merge tooling. Possible future v2 work; not v1.
- **Aggressive auto-merge in the matcher.** Tried (tuning, fingerprint requirement). Reduces false positives but doesn't itself produce real stories — it only avoids creating *bad* ones.
- **Mixed approach: keep aggregation but only for stories that have very obvious clusters.** Considered. Adds complexity without clearly resolving the long tail of mid-confidence items.

## Consequences

**Positive:**
- ~50 hours of manual triage avoided.
- No editorial bottleneck — corpus grows freely, retrieval handles dedup automatically.
- Retrieval-side dedup scales to any corpus size, including future audio transcriptions.
- Simpler architecture: chunks are the unit of retrieval, period. No story layer to maintain.

**Negative:**
- No clean "compare narrators" UX (was a v2 mode candidate). Would need a separate mechanism to rebuild later.
- No curated "this is the best telling of X" editorial artifact.
- Chat attributions are *source-file-based* (`from श्रीसोनोपंत दांडेकर compilation, segment 3`) rather than *story-based* (`from the story of Sonopant's surgery experience`). Slightly less narrative-feeling.
- The Phase 1 work on `tools/ingest_athvani.py` and the matcher tuning are no longer load-bearing for the demo. The script is kept around but inactive.

## Implementation impact

- **RFC-003** is amended to include the three dedup layers in the retrieval and generation pipeline (see §Retrieval, §Generation).
- **RFC-004 §Modes** drops "Compare Narrators" as a v2 candidate (was already aspirational).
- The placeholder stories created during bulk ingest are deleted; the seeded `the-old-house-at-nimbal` is kept as a working example of the structure, but not as a live corpus entry.
- The chunker (task #23) reads from canonical `text.md` files, athvani variant `.md` files, and biography `text.md` files. Raw athvani DOCX files in `02_aggregated/athvani/<member>/raw/` will be extracted to text on-the-fly during chunking.

## References

- [RFC-003 Retrieval & RAG strategy](../rfc/RFC-003-retrieval-and-rag.md) — amended for the 3 dedup layers
- [RFC-004 Chat UI & UX](../rfc/RFC-004-chat-ui-and-ux.md) — Compare Narrators mode dropped from v2 candidates
- Conversation 2026-06-14 — user asked for a better dedup approach after the matcher surfaced 562-item manual triage burden
