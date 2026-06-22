# ADR-005: Raw zip is the immutable archive; extracted staging uses move semantics

**Status:** ACCEPTED
**Date:** 2026-06-11 (decided), 2026-06-12 (documented)
**Author:** Neha (with Claude)

## Context

The corpus is being assembled in batches. Each batch arrives as one or more Google Drive zip files (e.g., `Neha-20260611T212253Z-3-001.zip`, ~2 GB). Once extracted, files need to flow out of staging into structured locations under `01_canonical/`, `02_aggregated/`, `03_catalog/reference/`, or `00_raw/_skipped/`.

The architectural question: as files flow out of staging, do we **copy** (preserve original in staging) or **move** (file leaves staging, lands once in its final home)?

The initial README (written before this question was settled) implied a copy model: "Raw files in `00_raw/` are immutable. Everything downstream can be re-derived from them." That model duplicates ~2 GB per batch, but means staging is forever an authoritative archive.

In practice, when the first ~50 files were being categorized, this became impractical:
- Disk cost grows linearly with batch count.
- "Re-derive from raw" is rarely needed — most downstream work writes new files (extracted text, meta.yaml) rather than re-transforming source files.
- The zip itself is the truly canonical archive — files in extracted staging are just *one decoded copy* of the zip's contents.

## Decision

- **The zip is the immutable archive.** Each batch's zip stays in `00_raw/` indefinitely.
- **Extracted staging is a working area** — `00_raw/drive_dump_YYYY-MM-DD/`. Files MOVE out of staging as they're cataloged (into `01_canonical/...`, `02_aggregated/...`, etc.).
- **No source duplicates in structured locations.** When a file is moved into `01_canonical/.../source.pdf`, it is no longer in staging.
- **Recovery story:** if a categorized file is mis-placed or we need to re-extract, we re-decompress the zip into staging and re-do the move. Effort, not loss.

Per-batch staging folders use the format `drive_dump_YYYY-MM-DD/<contributor>/` so multiple batches can coexist without collision and contributor provenance is preserved.

## Alternatives considered

- **Copy semantics** (original) — each batch keeps a full extracted copy forever. Rejected: ~2 GB per batch is real disk pressure once we have 5–10 batches.
- **Delete the zip after categorizing** — minimum disk usage, but loss of the canonical archive. Rejected: zips are cheap to keep and irreplaceable if accidentally deleted upstream.
- **Hard links** (one inode, multiple paths) — clever but fragile across filesystems and confusing for human users. Rejected as over-engineering.

## Consequences

**Positive:**
- Disk-efficient. One copy of each file, plus the small zip.
- The zip is the single immutable source-of-truth — easy to back up, easy to share with future contributors.
- Staging folder becoming "empty" after a batch is fully categorized is a clear signal of completion.

**Negative:**
- If a categorized file is wrongly placed and the move is also lost (e.g., user deletes a directory), we depend on the zip to recover. This is fine as long as the zip is preserved.
- A future contributor reading the README must understand that `01_canonical/.../source.pdf` IS the working copy — there's no backup beyond the zip. Worth restating in the corpus README when it gets updated.

## References

- [PRD.md §3 Phase 1](../PRD.md)
- RFC-002 (Corpus structure) — full directory contract
- Project memory: `project_gurudev_corpus.md`
