# Architecture Decision Records (ADRs)

An ADR captures a single significant decision: what we chose, why, what we considered, what the consequences are. ADRs are **append-only history** — never edit a past ADR to reflect a new decision; write a new ADR that supersedes it.

## When to write an ADR

- Any decision that constrains future implementation choices
- Any decision someone might later ask "why did we do that?" about
- Any non-obvious technology/library/framework choice
- Any decision that overrides a default or convention

Not needed for: trivial choices, decisions covered by an accepted RFC (reference the RFC instead).

## ADR format

Name: `ADR-NNN-short-slug.md`. NNN is zero-padded sequence number.

### Required sections

```markdown
# ADR-NNN: Title (active voice — "Use X for Y", "Adopt Z")

**Status:** [PROPOSED | ACCEPTED | SUPERSEDED by ADR-XXX | DEPRECATED]
**Date:** YYYY-MM-DD
**Author:** name

## Context
What's the situation that forced this decision? What are the constraints?

## Decision
The decision itself. Crisp, ~1 paragraph.

## Alternatives considered
2+ alternatives, each with a reason it wasn't chosen.

## Consequences
What does this enable, prevent, or commit us to? Both positive and negative.

## References
Related RFCs, ADRs, external links.
```

ADRs should be short — 1 page is ideal, 2 pages is the upper limit.

## Lifecycle

1. **PROPOSED** — drafted, under review
2. **ACCEPTED** — committed to
3. **SUPERSEDED by ADR-XXX** — replaced; add forward link, note date of supersession
4. **DEPRECATED** — abandoned (state why)

Status changes are noted at the top of the document, dated. **Do not delete or rewrite — only update status and add a "Superseded" note.**

## Index

| # | Title | Status | Date |
|---|---|---|---|
| [001](ADR-001-treat-as-system-design.md) | Treat Gurudev Corpus as a formal system design project | ACCEPTED | 2026-06-12 |
| [002](ADR-002-lineage-aware-folder-structure.md) | Organize canonical and aggregated content by lineage member | ACCEPTED | 2026-06-11 |
| [003](ADR-003-anthropic-api-not-subscription.md) | Use Anthropic API for Phase 2 (not Claude.ai consumer subscription) | ACCEPTED | 2026-06-12 |
| [004](ADR-004-bilingual-from-day-one.md) | Support English + Marathi from day 1 (input and output) | ACCEPTED | 2026-06-12 |
| [005](ADR-005-raw-zip-immutable-staging-uses-move.md) | Raw zip is the immutable archive; extracted staging uses move semantics | ACCEPTED | 2026-06-11 |
| [006](ADR-006-warm-devotional-aesthetic.md) | Visual aesthetic — "warm devotional, old yellow pages, maroon paprika" | ACCEPTED | 2026-06-12 |
| [007](ADR-007-quote-first-curation-pattern.md) | Adopt quote-first curation pattern over LLM synthesis | ACCEPTED | 2026-06-13 |
| [008](ADR-008-skip-story-aggregation-dedup-at-retrieval.md) | Skip story aggregation; dedup at retrieval and generation time | ACCEPTED | 2026-06-14 |
| [009](ADR-009-embedding-model-e5-small.md) | Embedding model — multilingual-e5-small | ACCEPTED | 2026-06-14 |
| [010](ADR-010-qa-doctrinal-vs-meta-classification.md) | Q&A internal classification — doctrinal (quote-first) vs meta (plain prose) | ACCEPTED | 2026-06-14 |
| [011](ADR-011-structured-output-contract.md) | Structured-output JSON contract for `/api/ask` via tool-use | PROPOSED | 2026-06-17 |
| [012](ADR-012-chunk-id-keyed-embeddings.md) | Chunk-id-keyed embeddings + sorted chunker scan | ACCEPTED | 2026-06-17 |
| [013](ADR-013-reading-mode-real-data-path.md) | Reading mode — real-data backend endpoint, pagination, and citation deep-links | ACCEPTED | 2026-06-25 |
| [014](ADR-014-conversational-followups-with-history.md) | Conversational follow-ups carry history and new-material enforcement | ACCEPTED | 2026-06-25 |
