# RFC Process

An RFC (Request for Comments) is a focused technical design document for one component. Each major implementation effort references an accepted RFC.

## When to write an RFC

- Before building a new component (chat UI, retrieval pipeline, deployment infrastructure)
- Before making a non-trivial architecture change to an existing component
- Before adopting a new library, framework, or external service

Not needed for: bug fixes, minor refactors, single-file utilities.

## RFC format

Each RFC is a single Markdown file. Name: `RFC-NNN-short-slug.md` where NNN is the next available number (zero-padded), and slug is kebab-case (e.g., `RFC-003-retrieval-and-rag.md`).

### Required sections

```markdown
# RFC-NNN: Title

**Status:** [PROPOSED | ACCEPTED | SUPERSEDED by RFC-XXX | DEPRECATED]
**Author:** name
**Created:** YYYY-MM-DD
**Last updated:** YYYY-MM-DD

## Summary
1–2 sentence pitch.

## Motivation
Why does this need designing? What problem are we solving?

## Goals & non-goals
- Goal 1
- Goal 2
- Non-goal 1

## Proposed design
The actual technical proposal. Diagrams, code sketches, data flow.

## Alternatives considered
2+ alternative designs, each with a paragraph on why we didn't pick it.

## Tradeoffs & risks
What's the cost of this design? What could go wrong?

## Open questions
Things we haven't resolved yet.

## References
Related RFCs, ADRs, external links.
```

## Lifecycle

1. **PROPOSED** — drafted, under review
2. **ACCEPTED** — signed off, implementation may begin
3. **SUPERSEDED** — replaced by a later RFC (link forward)
4. **DEPRECATED** — abandoned (state why)

Status changes are noted at the top of the document, dated.

## Index

| # | Title | Status |
|---|---|---|
| [001](RFC-001-demo-mvp.md) | Demo MVP scope (July 12) | ACCEPTED |
| [002](RFC-002-corpus-structure.md) | Corpus structure | ACCEPTED |
| [003](RFC-003-retrieval-and-rag.md) | Retrieval & RAG strategy | ACCEPTED |
| [004](RFC-004-chat-ui-and-ux.md) | Chat UI & UX | ACCEPTED |
| [005](RFC-005-multilingual-strategy.md) | Multilingual (EN + MR) strategy | ACCEPTED |
| 006 | Access control & invite system | future |
| 007 | Deployment & hosting | future |
| 008 | Audio recordings + transcription | future |
| [009](RFC-009-corpus-ingestion-pipeline.md) | Corpus ingestion pipeline (new-material runbook) | ACCEPTED |
| [010](RFC-010-progressive-streaming.md) | Progressive streaming for the answer surface | ACCEPTED |
| [011](RFC-011-intent-aware-citation-ranking.md) | Intent-aware citation ranking | PROPOSED |
