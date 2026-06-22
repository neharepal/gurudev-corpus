# ADR-012: Chunk-id-keyed embeddings + sorted chunker scan

**Status:** ACCEPTED
**Date:** 2026-06-17
**Author:** Neha (with Claude)
**Closes:** [RFC-009 §Risks §1, §Open Questions §1](../rfc/RFC-009-corpus-ingestion-pipeline.md)

## Context

The corpus has two long-running artifacts that are linked by row index:

- `04_processed/chunks.jsonl` — one JSON line per chunk, position determines its identity in the index.
- `04_processed/embeddings/embeddings.npy` — float32 (N, dim), L2-normalized; row N is the vector of chunk N in `chunks.jsonl`.

The chunker (`tools/chunker.py`) rewrites `chunks.jsonl` from scratch on every run, walking the corpus with bare `Path.iterdir()`. The embedder (`tools/embedder.py`) computed `embeddings.npy` by encoding each row in order and keyed everything — including resumable progress checkpoints — by **row index**.

This coupling was fragile in a way RFC-009 §Risks §1 had already flagged but not yet fixed. Two pre-existing facts made it actively dangerous:

1. **`iterdir()` is non-deterministic.** APFS uses insertion order in its B-tree; ext4 uses hashed entries; both can shuffle after create/delete cycles. The same corpus state could produce different `chunks.jsonl` orderings across machines or across runs on one machine. We had been getting away with it only because no batch had been added since the original embedding run.
2. **The embedder treated row index as identity.** A row-N vector was bound to whatever text happened to be at row N of `chunks.jsonl` *at the time of encoding*. If the file was later rewritten and the chunk at row N was different, the embedding silently mismatched its text. Search would surface a high-similarity row, but the displayed text was the wrong passage.

The Wikimedia ingestion on 2026-06-17 hit both at once. The ingestion agent added 16 books, re-ran the chunker, and produced a `chunks.jsonl` where 83 of 86 pre-existing works had shifted row indices (filesystem iteration order was different from the original embedding run). The existing `embeddings.npy` was now misaligned: row N in the vector store was bound to the *old* row-N chunk, but the new `chunks.jsonl` row N pointed to a different work entirely.

Two options to recover:

- Run `embedder.py --restart` overnight (~14h) — brute-force rebuild the whole index from scratch.
- Fix the underlying coupling so future re-chunks don't invalidate the prior embeddings.

We took the second path. This ADR documents the design.

## Decision

Two changes, deployed together:

### 1. Chunker scan order is deterministic.

`tools/chunker.py` gained a `_sorted_dir(path)` helper that returns `sorted(path.iterdir(), key=lambda p: p.name)`. Every `iterdir()` call inside the canonical/biography/athvani/periodicals/reference scan loops was rewritten through this helper.

After this change, the same corpus state produces the same `chunks.jsonl` bit-for-bit across machines and across runs. The contents of `chunks.jsonl` become a pure function of `01_canonical/` + `02_aggregated/` + `03_catalog/reference/` + `00_raw/` athvani — not a function of when the directory entries were created.

### 2. Embeddings are keyed by `chunk_id`, not row index.

Every chunk already carries a stable identifier (`maharajachi-sutre--mr--0000`, `bhakti-sutras--en--0042`, etc.) composed of `{work_id}--{language}--{chunk_index_within_work}`. The embedder was rewritten so that on every run:

1. Read the existing `embeddings.npy` + `chunks_meta.jsonl`. Build a `{chunk_id → vector}` map in RAM (~28 MB for 7k chunks).
2. Read the new `chunks.jsonl`.
3. For each chunk in the new file:
   - If its `id` is in the map → copy the vector to its new row.
   - If its `id` is not in the map → schedule the chunk for encoding.
4. Allocate a fresh `embeddings.npy` memmap sized to the new corpus.
5. Write the carry-over rows in one fast pass.
6. Encode the new chunks in batches.

The embedder no longer treats row index as identity. Row index is a presentation artifact of the current `chunks.jsonl` ordering. Identity is the `chunk_id`.

### Concrete measurement from the deployment run (2026-06-17)

- Existing embeddings: 6,924 rows, 6,908 distinct `chunk_id`s in the map.
- New `chunks.jsonl` after the 16-book ingestion: 13,027 rows.
- Carry-over: 6,924 rows — every pre-existing chunk's vector was reused as-is, **completed in 0.1 seconds**.
- New work: encode 6,103 net-new chunks (~8.5h on this Intel CPU at BGE-M3 throughput).
- Without this change: a `--restart` run would have re-encoded all 13,027 rows (~14h), throwing away 11 hours of valid prior compute.

For *future* batches the asymmetry is much more dramatic. A typical small ingest is 1–2 books = ~200 chunks. Under the new scheme that's a ~20-minute incremental embed. Under the old scheme it would still have been the full 14h rebuild.

## Consequences

### Positive

- **Re-chunking is safe.** A batch can be added, removed, re-classified, or moved between authors without invalidating any embedding the new chunk's ID still resolves to.
- **Re-runs are idempotent.** Running the embedder twice in a row with no corpus changes does nothing (the manifest matches and short-circuits; if it didn't, every row would carry over).
- **Crashes recover correctly.** The new embedder snapshots the pre-run `embeddings.npy` + `chunks_meta.jsonl` to `.preincremental.bak.*` sidecars at the start of every run. On resume after a crash, the id→vec map is rebuilt from the snapshot (because the active `embeddings.npy` has been partially overwritten). The snapshot is deleted on successful completion.
- **Model switches are safe.** A new `--model` (or a manifest that says a different model) triggers `archive_existing(...)` which MOVES the prior build into `embeddings/_archive/<model>-<ts>/`. The id→vec map starts empty, every row encodes fresh. Per ADR-009, hard-earned embeddings are never thrown away — they're preserved in the archive in case we want to compare or fall back.
- **No application-side change.** `retrieve.py` and `tools/server.py` keep reading `embeddings.npy` as a row-aligned float32 matrix. They are agnostic to *how* the rows got there. The new chunk-id-keyed scheme is purely an embedder-internal concept.

### Negative

- **~28 MB RAM at the start of each embed run** to hold the existing id→vec map. Negligible.
- **One extra disk copy per run** to make the snapshot sidecar. About 28 MB for the current corpus; not a practical concern.
- **Embedder code grew from 312 LOC to ~430 LOC.** Most of the new code is the snapshot/resume logic and the carry-over partition. Acceptable given how load-bearing this is.

### Known limitations not addressed by this ADR

- **Pre-existing chunk_id collisions.** The current chunker emits the same id (`{work_id}--{lang}--{chunk_index}`) for any two chunks that share `(work_id, lang, chunk_index)`. The corpus today has 16 such collisions — they're all from a Marathi work `१९१४-१९२७` which appears to be ingested from two different source paths, both producing the same work_id slug. The old `chunks_meta.jsonl` already had this problem (6,924 rows → 6,908 distinct IDs). The new embedder handles collisions by taking whichever vector arrived last in the map — the same behavior as before. Fixing the collisions properly is a chunker change: derive a fully-qualified id from the source path, not just from the work slug. **Tracked separately**, not blocking this ADR.

## Alternatives considered

### A. Brute-force rebuild every batch (`embedder.py --restart`)

The simplest possible response: every batch incurs the full rebuild cost. On this Intel CPU that's 11–14 hours. Untenable at any meaningful ingestion cadence. Rejected.

### B. Append-only `chunks.jsonl`

Have the chunker only append new chunks; never rewrite existing rows. The embedder could then keep treating row index as identity (rows never move).

Rejected for two reasons:

1. It only solves the "add" case. If a work is edited (text fix, translation update, retraction), its existing chunks linger as stale rows that retrieval still surfaces. No clean way to invalidate.
2. Append-only ordering depends on operational history, not on the current corpus state. Two contributors running the chunker on the same corpus in different orders would get different `chunks.jsonl` files — same problem as `iterdir()` non-determinism, just on a different axis.

### C. Periodic full rebuild as a maintenance job

Use the incremental scheme for daily work; run `--restart` weekly to catch drift. Adds operational complexity (the maintenance job has to be remembered and respected), and is solving a problem that doesn't exist if the incremental scheme is correctly designed. Rejected.

### D. Move to a vector database (Qdrant / pgvector / etc.)

A real vector DB would solve identity-by-ID natively. Worth doing eventually, but a heavy lift right now (RFC-007 deployment territory, schema migration, ops overhead). The current `.npy` + `.jsonl` files are working — the issue was design, not storage substrate. Deferred.

## Implementation notes for future contributors

- `tools/chunker.py:_sorted_dir(path)` is the canonical sort helper. Use it for every directory walk, including any new scan functions added in the future (new content categories).
- `tools/embedder.py:build_id_to_vec(emb_path, meta_path, expected_dim)` is the canonical rehydration routine. It returns `{}` defensively when files are missing, dimensions mismatch, or row counts disagree. Treat its return value as authoritative.
- The `.preincremental.bak.*` snapshot sidecars are managed by `snapshot_existing_for_resume()` + `cleanup_snapshot()`. They live next to the active embeddings; they should never be checked in. Either snapshot existing or not at all — partial snapshots get archived to `_archive/` on the next `archive_existing()` call.
- If the chunker ever emits a chunk without an `id` field, the embedder will treat it as new (no carry-over possible). Don't rely on this — assign an id.

## References

- RFC-009: Corpus ingestion pipeline (the runbook that flagged this risk)
- ADR-005: Raw zip is the immutable archive (the "move, don't copy" principle that informs how `_archive/` works)
- ADR-009: Embedding model BGE-M3 (the manifest-based model-switch detection)
- `tools/chunker.py`, `tools/embedder.py`, `tools/retrieve.py`
- Deployment notes (2026-06-17): `04_processed/embeddings/manifest.json` for the current run; `docs/CORPUS_CHANGELOG.md` for the batch entry
