# HANDOVER — Migrate to M4 + Phase-2 re-embed (one operation) — 2026-07-15

For the Claude picking this up **on the M4**. The project is moving from the Intel Mac
(daily driver, PyTorch capped at 2.2.2, CPU-only) to this M4 (latest stack + MPS GPU).
The Surya re-OCR just completed, and it has merged with the Phase-2 cutover — so the
migration and the Phase-2 re-embed are now the SAME job. Do them together.

## State you're inheriting (all pushed to git as of this doc)
- **Corpus text is clean.** 15 garbled tesseract books were re-OCR'd with Surya on this
  M4 and their `text.md` replaced in place (commit `f10cd21`). Backups of the tesseract
  originals are in `04_processed/_bak-reocr-2026-07-15/` (gitignored, on the Intel Mac).
- **Phase-2 chunking is already done.** `tools/chunker.py` was run on the Intel Mac and
  produced the small-to-big index:
  - `04_processed/chunks.jsonl` — **282,126 children** (verified: every child maps to a
    parent; all carry `cite_text`; clean Surya text inside).
  - `04_processed/parents.jsonl` — **15,920 parents**.
  These are RFC-017 / RUNBOOK-phase2-reembed.md **Step 1 output** — the embed input.
- **The old index is NOT reusable.** `04_processed/embeddings/` (16,888 section-chunk
  vectors) was built from the OLD garbled text and is row-aligned to a `chunks.jsonl` that
  no longer exists (the Phase-2 re-chunk overwrote it). Do not try to serve it. The
  Phase-2 re-embed replaces it wholesale — that's the point.

## What to copy from the Intel Mac (gitignored, so manual — SSD/AirDrop)
Required for the re-embed:
- `04_processed/chunks.jsonl` (282k children) + `04_processed/parents.jsonl`
Also bring:
- `00_raw/` (~13 GB) — source scans, for any future re-OCR / re-ingest
- `photos/` (~53 MB) — reader/app assets
Do NOT copy (regenerated on the M4): `04_processed/embeddings/` (rebuilt by the re-embed),
`chat-app/node_modules/`, any venvs, the HuggingFace cache (`~/.cache/huggingface`).

## Steps on the M4
1. **Code:** `git clone` (everything is pushed). `pip install -r requirements.txt`
   (torch resolves to the latest arm64 + MPS build here). `npm install` in `chat-app/`.
2. **Re-embed (the heavy step):** follow `docs/RUNBOOK-phase2-reembed.md` from **Step 2**,
   but run it **natively on this M4's MPS GPU** — no cloud GPU needed (that's the whole
   reason we moved here). Embed `04_processed/chunks.jsonl` → `embeddings.npy` +
   `chunks_meta.jsonl`, row-aligned to the children. ~282k short texts on BGE-M3; budget a
   few hours. Confirm MPS is engaged (`torch.backends.mps.is_available()`), else you're on
   CPU and it'll crawl.
3. **Verify alignment** (RUNBOOK Step 3): rows(embeddings) == len(chunks_meta) ==
   len(chunks.jsonl), every meta has `parent_id`, dim == 1024. STOP if misaligned.
4. **Finish Phase 2 build** (RFC-017 Tasks 6/7/8 — not yet done): flag-gated
   `ENABLE_SMALL_TO_BIG` child→parent expansion in `_retrieve` (helpers
   `expand_children_to_parents` + `STATE.parents_by_id` already merged), splice/Read-in-full
   on `cite_text`, and `eval_retrieval.py` gold cases (incl. the "lightning" recall case and
   an arthasahit cite-the-verse-only case). Smoke-test with `ENABLE_SMALL_TO_BIG=1` before
   defaulting it on. See `.superpowers/sdd/progress.md` for Task status.
5. **Run the app**, verify end-to-end (a query hitting a re-OCR'd book should now cite clean
   Surya text), then the M4 is the daily driver. Retire the Intel Mac only after this.

## Notes
- The Intel Mac's server (PID from that session) is serving the old in-memory index and
  must not be restarted there — irrelevant once this M4 index is live.
- Re-OCR needed no separate re-embed: the clean text is already in `chunks.jsonl`, so it
  rides the Phase-2 rebuild for free (the "Option A" decision).
- Related docs: `docs/RUNBOOK-phase2-reembed.md`, `docs/rfc/RFC-017-*.md`,
  `docs/HANDOVER-2026-07-14-surya-ocr-m4.md` (the OCR job that produced this text),
  `tools/surya_ocr/` (the return-side tooling, already applied).
