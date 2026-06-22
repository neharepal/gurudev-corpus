# Gurudev Corpus — Documentation

This folder is the single source of truth for project design and decisions. **Do not implement anything not documented here.**

## Hard deadline

**July 12, 2026** — sampradaya meeting demo. The corpus + chat must run end-to-end on a local browser by that date.

## Documents

### Top-level

- **[PRD.md](PRD.md)** — Product Requirements Document. The *what*, *why*, and *for whom*. Single source of truth for scope and success criteria.
- **[roadmap.md](roadmap.md)** — Timeline backward-planned from July 12. Week-by-week milestones, critical path.

### RFCs (Request for Comments — technical design)

One RFC per major component. Implementation tasks reference their RFC by number.

- **[rfc/](rfc/)** — see [rfc/README.md](rfc/README.md) for the RFC process.

| # | Topic | Status |
|---|---|---|
| 001 | Demo MVP scope (July 12) | not started |
| 002 | Corpus structure (Phase 1) | not started |
| 003 | Retrieval & RAG strategy | not started |
| 004 | Chat UI & UX | not started |
| 005 | Multilingual (EN + MR) strategy | not started |
| 006 | Access control & invite system | future |
| 007 | Deployment & hosting | future (post-demo) |
| 008 | Audio recordings + transcription | future |

### Decision Log (ADRs — Architecture Decision Records)

Chronological log of decisions. Each ADR is short (~1 page) and captures: context, decision, alternatives considered, consequences.

- **[decisions/](decisions/)** — see [decisions/README.md](decisions/README.md) for the ADR process.

## How to navigate

- **"What are we building and why?"** → PRD
- **"When does X happen?"** → roadmap
- **"How is component X designed?"** → its RFC
- **"Why did we choose X over Y?"** → search ADRs
- **"What's left to do?"** → ask Claude `show task list`

## Document conventions

- All docs are Markdown.
- Headings start at H1 (`#`) for the doc title, H2 (`##`) for sections.
- Cross-link generously: `[ADR-002](decisions/ADR-002-lineage-aware-folders.md)`.
- Date all entries (ISO format `YYYY-MM-DD`).
- Status badges where useful: `[PROPOSED]`, `[ACCEPTED]`, `[SUPERSEDED]`, `[DEPRECATED]`.
