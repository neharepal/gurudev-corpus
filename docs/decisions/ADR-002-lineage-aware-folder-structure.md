# ADR-002: Organize canonical and aggregated content by lineage member

**Status:** ACCEPTED
**Date:** 2026-06-11 (decided), 2026-06-12 (documented)
**Author:** Neha (with Claude)

## Context

The corpus material spans multiple gurus in the Nimbal sampradaya parampara:

- Nimbargi Maharaj (lineage founder)
- Bhausaheb Maharaj (disciple of Nimbargi)
- Amburao Maharaj and Shri Gurudev Ranade (peer disciples of Bhausaheb)
- Kakasaheb Tulpule (later disciple/expositor in the tradition)

Plus other devotees and authors who contributed athvani (recollections), commentary, or biographical material.

The original scaffold used a flatter layout (`01_canonical/gurudev/books/`, `kakasaheb_tulpule/`, `other_authors/`) that handled only two named authors. As soon as the first Drive zip was unpacked it became clear that:

1. Athvani folders exist for *each* lineage member (Nimbargi, Bhausaheb, Amburao, Gurudev), not just Gurudev.
2. Canonical works exist for multiple members (Nimbargi's Bodhsudha, Bhausaheb's works, Kakasaheb's pravachans, Ranade's books).
3. Phase 2 retrieval will need to *filter by guru* — e.g., "what does Bhausaheb teach about X?" — which requires lineage to be a first-class index dimension.

## Decision

Both `01_canonical/` (works by an author) and `02_aggregated/athvani/` (stories about a person) use **per-lineage-member subfolders**:

```
01_canonical/
  nimbargi_maharaj/
  bhausaheb_maharaj/
  amburao_maharaj/
  gurudev_ranade/
  kakasaheb_tulpule/
  other_authors/

02_aggregated/athvani/
  about_nimbargi_maharaj/
  about_bhausaheb_maharaj/
  about_amburao_maharaj/
  about_gurudev_ranade/
  about_other_devotees/
```

The `about_` prefix on athvani folders makes the *subject* explicit (a story *about* Bhausaheb, not *by* Bhausaheb).

A work folder for each canonical title sits under the author's folder, then per-language subfolders:

```
01_canonical/gurudev_ranade/books/pathway-to-god-in-hindi-literature/en/source.docx
01_canonical/nimbargi_maharaj/books/bodhsudha/mr/source.pdf
```

## Alternatives considered

- **Flat structure** (all works in one directory, author/lineage in `meta.yaml`). Simpler filesystem, but cumbersome browsing and Phase 2 retrieval has to filter at query time rather than at index time. Rejected — lineage is too load-bearing to leave in metadata only.
- **Tag-based** (no author folders; works tagged with `lineage_member: gurudev_ranade`). Maximum flexibility but extra metadata overhead and the filesystem stops being a useful navigation aid.
- **Chronological / by-period structure** (early/middle/late Gurudev). Useful for biographers but mostly orthogonal to how devotees ask questions.

Lineage-aware folders are the structure that closest matches how the audience *thinks* about the material — by guru, in lineage order — and is also how Phase 2 retrieval will filter most often.

## Consequences

**Positive:**
- Phase 2 RAG can filter retrieval by author/lineage at the index level (cheap and precise).
- File-system navigation matches the mental model of devotees: "show me Bhausaheb's works."
- New lineage members or contributors get a clear home (`other_authors/` for non-named contributors; new lineage members get their own folder).
- Athvani aggregation respects subject — when a story is told *about* Bhausaheb, it lives under `about_bhausaheb_maharaj/`, regardless of which narrator told it.

**Negative:**
- Works by/about multiple lineage members (joint biographies, comparative essays) have an ambiguous home. Mitigation: pick the primary subject and link from others via the catalog.
- Lineage corrections (e.g., correcting a misattribution) require moving folders. Mitigation: keep slugs stable, use catalog redirects if needed.
- Initial structure rework was needed when the lineage detail became clear — done via a background agent in one pass.

## References

- [PRD.md §2 Audience, §3 Phase 1](../PRD.md)
- [docs/README.md](../README.md) — folder map
- Project memory: `project_gurudev_corpus.md` (lineage corrections)
