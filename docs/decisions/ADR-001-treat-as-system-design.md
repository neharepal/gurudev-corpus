# ADR-001: Treat Gurudev Corpus as a formal system design project

**Status:** ACCEPTED
**Date:** 2026-06-12
**Author:** Neha (with Claude)

## Context

The Gurudev Corpus project (Phase 1 corpus + Phase 2 chat platform) serves a sampradaya community of ~500 devotees, has a hard July 12, 2026 demo deadline, and will be the canonical source of truth for spiritual literature spanning several languages and a multi-guru lineage.

The first ~24 hours of work were implementation-first: scaffolding folders, ingesting Drive zips, building an attribution dashboard, walking one athvani end-to-end. Decisions accumulated without documentation. As the implementation surface grew (5+ structural decisions, the bilingual scope shift, the demo deadline, multiple modes, hosting constraints), it became clear that continuing in vibe-code mode would (a) make the project hard to hand off, (b) accumulate hidden assumptions, (c) lose decision rationale, and (d) risk scope drift against the immovable July 12 date.

## Decision

Treat the project as a **formal system design project** with three artifact types:

1. **PRD** (one document) — the *what*, *why*, *for whom*, success criteria, scope, constraints. Single source of truth.
2. **RFCs** (one per major component) — technical design proposals. Implementation work does not begin until the corresponding RFC is accepted.
3. **ADRs** (this format, growing log) — chronological record of significant decisions, why we made them, what alternatives we considered, what consequences we accepted.

All three live in `gurudev-corpus/docs/` and are version-controlled alongside the corpus.

## Alternatives considered

- **Vibe-code, document later.** Faster initial velocity but rapidly accumulates undocumented decisions. Becomes nearly impossible to onboard a second contributor. Rejected because the corpus needs to survive Neha's eventual handoff.
- **Lightweight one-pager only.** Captures top-level decisions but not the rationale or alternatives. Insufficient for a project of this scope with a meaningful audience.
- **Heavyweight enterprise process** (PRD + spec + design + test plan + ops runbook + ...). Too much overhead for a one-person project on a 30-day clock.

PRD/RFC/ADR is the lightest discipline that captures *what*, *how*, and *why* — the three questions a future contributor (or future-Neha after a gap) will ask.

## Consequences

**Positive:**
- Decisions traceable. Anyone (future-Neha, future contributors, even me on a later session) can reconstruct why X exists.
- Implementation tasks reference their RFC; scope creep is visible because changes require updating the doc first.
- Demo-vs-production tradeoffs are explicit, not hidden.
- The corpus itself benefits — the same discipline that catalogs Gurudev's works also catalogs our own design choices.

**Negative:**
- ~5 days of design work upfront before sprinting on implementation. Tight against July 12 but worth it.
- Future small decisions may still get rushed — discipline takes effort.
- Documentation can rot if not updated when decisions change. We mitigate by appending new ADRs that supersede old ones, never editing past ones.

## References

- [PRD.md](../PRD.md)
- [docs/README.md](../README.md)
- Project memory: `feedback_owns_structure.md`, `project_gurudev_corpus_design_mode.md`
