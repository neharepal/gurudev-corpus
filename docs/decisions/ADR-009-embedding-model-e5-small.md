# ADR-009: Use multilingual-e5-small for embeddings (override RFC-003's BGE-M3)

**Status:** REVERSED — see "Reversal" below. Net decision: **stay on BGE-M3** (RFC-003 unchanged); keep e5-small only as a documented fallback.
**Date:** 2026-06-15
**Author:** Neha (with Claude)

## Reversal (2026-06-15, same day)

The premise of this ADR — that BGE-M3 is unworkably slow on this machine — was **largely wrong**.
The macOS power log showed the laptop **slept repeatedly during the BGE-M3 run** (a ~2h
*Clamshell Sleep* from a closed lid, plus ~1h + ~35m + ~50m of maintenance/idle sleeps). The
process was *suspended*, not computing slowly; wall-clock kept advancing, so tqdm's rate/ETA
collapsed and looked like a "death spiral." The clean, sleep-free benchmark was ~5.9s/chunk
(~0.17/s) → **~11–15h of actual compute**, i.e. a normal overnight job.

**Net decision: keep BGE-M3** for full retrieval quality (RFC-003 stands), and run it correctly:
wrapped in `caffeinate`, **plugged into AC with the lid open** (caffeinate does NOT prevent
clamshell sleep — an open lid does). e5-small remains a documented fallback if BGE-M3 ever proves
too slow for the workflow, selectable via `tools/embedder.py --model intfloat/multilingual-e5-small`.

Also fixed: `tools/embedder.py` now **archives** (never deletes) existing embeddings on a model
switch or `--restart`, into `04_processed/embeddings/_archive/<model>-<ts>/`. The original loss of
the BGE-M3 partial was a manual `rm` during the switch, not a tooling failure — this makes that
class of mistake impossible going forward.

The analysis below is retained as the record of the (incorrect) reasoning that led here.

---

## Context

RFC-003 selected **BAAI/bge-m3** as the embedding model — a strong multilingual
retriever (EN + MR + HI + SA + KN). That choice was made on capability grounds
without benchmarking it on the actual hardware.

When we ran the embedding build on the real corpus (6,924 chunks), BGE-M3 proved
unworkable on this machine:

- **Hardware:** Intel Core i5-1038NG7, 4 cores @ 2.0 GHz, no usable GPU/MPS.
- **Model size:** BGE-M3 is XLM-RoBERTa-large, ~560M params, ~2.2 GB resident in float32.
- **Measured throughput:** ~0.13 chunks/s at best, degrading to **~0.03 chunks/s** as the
  machine warmed up and the model thrashed in swap (RSS ~2 GB on a memory-constrained box).
- **Result:** after **~14 hours wall-clock the run had completed only 19%** (1,328 / 6,924).
  It is FLOP-bound, not thread-bound — raising torch/OMP threads from 1→4 gave no speedup.
  ETA was projecting 40–60h and climbing.

This blocks the entire Phase 2 backend: retrieval cannot be built or demoed until
embeddings exist, and the July 12 demo is 27 days out. Holding the laptop hostage for
2+ days of embedding (while it's also needed for chat-app/UI development) is not viable.

## Decision

**Switch the embedding model to `intfloat/multilingual-e5-small`** for the demo build.

- ~118M params, 384-dim, ~5x smaller than BGE-M3 → projected **~1.5–2h** for the full
  corpus even under CPU contention.
- Still multilingual and covers the two demo languages (EN + MR) well; e5 is purpose-trained
  for retrieval, not just semantic similarity.
- e5 models require instructional prefixes: documents embedded as `passage: <text>`,
  queries as `query: <text>`. Both `tools/embedder.py` (passage side) and
  `tools/retrieve.py` (query side) updated accordingly. Mismatching the prefixes badly
  degrades retrieval, so they are kept in lockstep and keyed off the model name.

The rewritten `tools/embedder.py` (incremental memmap, resumable, progress bar) is model-agnostic;
only the model name, sequence length (512, e5-small's native max), and prefix handling changed.

## Alternatives considered

- **Keep BGE-M3, run overnight with the machine otherwise idle.** Rejected for the demo:
  still ~11h+ of exclusive machine time, fragile to any daytime use, and we'd rebuild anyway
  if quality on this corpus is fine with a smaller model (it is, for a demo).
- **paraphrase-multilingual-MiniLM-L12-v2** (also ~118M, no prefixes — simpler drop-in).
  Rejected: tuned for paraphrase/STS, weaker as a retriever than e5-small.
- **Hosted embedding API (e.g. Voyage).** Rejected for now: adds an external dependency and
  cost, and sends the devotional corpus off-device — undesirable for a private sampradaya archive.
- **Quantized/ONNX BGE-M3 (int8).** Deferred: 2–4x CPU speedup possible but adds toolchain
  complexity; revisit post-demo if we want BGE-M3 quality back.

## Consequences

**Positive:**
- Embedding build drops from ~unfinishable to ~2h; backend unblocked today.
- Smaller index (384-dim → ~10 MB vs ~28 MB) and faster query-time embedding.
- Embedder/retriever now handle model + prefix swaps cleanly, so reverting or upgrading later is a config change.

**Negative:**
- Lower ceiling on retrieval quality than BGE-M3, especially for cross-lingual and long-context
  nuance. Acceptable for a demo on EN + MR; flagged as a post-demo revisit.
- 512-token cap truncates the tail of the few longest chunks (corpus max ~800 tokens).
- Embeddings are model-specific: switching back to BGE-M3 later means a full re-embed (the build is cheap to redo and resumable).

## Implementation impact

- **RFC-003** amended: embedding model is multilingual-e5-small for the demo build; BGE-M3
  noted as a post-demo quality-upgrade option (revisit with quantization or better hardware).
- `tools/embedder.py`: `MODEL_NAME`, `DEFAULT_MAX_SEQ_LEN=512`, `passage:` prefix.
- `tools/retrieve.py`: `query:` prefix for e5 models; model name read from `manifest.json`,
  so the query side automatically tracks whatever the corpus was built with.
- Output contract unchanged (`embeddings.npy` float32 L2-normalized, `chunks_meta.jsonl`,
  `manifest.json`), so downstream retrieval/backend is unaffected beyond the dimension change.

## References

- [RFC-003 Retrieval & RAG strategy](../rfc/RFC-003-retrieval-and-rag.md) — amended; original BGE-M3 selection
- [project memory: embedding pipeline reality](#) — measured BGE-M3 throughput and the failed 14h run
- Conversation 2026-06-15 — BGE-M3 stalled at 19% after 14h; user approved switching to a smaller model
