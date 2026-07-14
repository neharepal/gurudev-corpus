#!/usr/bin/env python3
"""
Embed corpus chunks with chunk_id-keyed carry-over (ADR-012).

Reads:  04_processed/chunks.jsonl
Writes:
  04_processed/embeddings/embeddings.npy       — float32 (N, dim), L2-normalized, row-aligned to chunks.jsonl
  04_processed/embeddings/chunks_meta.jsonl    — per-chunk metadata, same row order as embeddings.npy
  04_processed/embeddings/manifest.json        — model, dim, chunk_count, built_at (written on completion)
  04_processed/embeddings/progress.json        — resume checkpoint over the NEW-rows-to-embed list
                                                  (deleted on completion)

Design (per ADR-012):
  1. ID-keyed carry-over. Each chunk has a stable `id` (e.g. "maharajachi-sutre--mr--0000").
     On every run we load the existing embeddings.npy + chunks_meta.jsonl into a
     {chunk_id → vector} map in RAM, then for the current chunks.jsonl:
       - if id present in map → copy the vector to its new row (no recompute)
       - if id is new          → schedule for encoding
     Result: re-running after any chunker re-scan touches only genuinely-new chunks.
  2. Sorted scan order. tools/chunker.py walks the corpus with sorted iterdir(), so
     chunks.jsonl is reproducible bit-for-bit across machines and runs. The ID-keyed
     scheme is robust to order shifts anyway, but stable order keeps diffs minimal.
  3. Crash-safe save. New embeddings stream into a pre-allocated .npy memmap, flushed
     every few batches. A kill/sleep loses at most one flush window.
  4. Resumable. progress.json tracks rows of the to-embed list already encoded. Re-run
     the same model: pick up where we left off. The carry-over map is rebuilt fresh
     from a sidecar .preincremental.bak snapshot (created at the start of every run).
  5. Never destroys embeddings. A model switch (different model name / dim) MOVES the
     existing build to embeddings/_archive/<model>-<ts>/ before starting fresh.
  6. Idempotent. If a completed manifest already matches the corpus state and model,
     short-circuit to no-op.
"""

from __future__ import annotations

# Thread env MUST be set before numpy / torch import to take effect for MKL/OMP.
import os

_PHYS_CORES = os.cpu_count() or 4
_THREADS = int(os.environ.get("EMBED_THREADS", str(max(1, _PHYS_CORES // 2)))) if (os.cpu_count() or 0) > 4 else _PHYS_CORES
os.environ.setdefault("OMP_NUM_THREADS", str(_THREADS))
os.environ.setdefault("MKL_NUM_THREADS", str(_THREADS))
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
CHUNKS_PATH = REPO / "04_processed" / "chunks.jsonl"
OUT_DIR = REPO / "04_processed" / "embeddings"
ARCHIVE_DIR = OUT_DIR / "_archive"
EMB_PATH = OUT_DIR / "embeddings.npy"
META_PATH = OUT_DIR / "chunks_meta.jsonl"
MANIFEST_PATH = OUT_DIR / "manifest.json"
PROGRESS_PATH = OUT_DIR / "progress.json"
# Sidecar snapshot of the pre-run embeddings, used to rebuild the id→vec map
# on a resume after a crash mid-encode. Deleted on successful completion.
PREINC_EMB = OUT_DIR / "embeddings.preincremental.bak.npy"
PREINC_META = OUT_DIR / "chunks_meta.preincremental.bak.jsonl"

DEFAULT_MODEL = "BAAI/bge-m3"
DEFAULT_BATCH_SIZE = 16
DEFAULT_FLUSH_EVERY = 4
DEFAULT_MAX_SEQ_LEN = 1024


def model_seq_len(model_name: str, requested: int) -> int:
    if "e5" in model_name.lower():
        return min(requested, 512)
    return requested


def passage_prefix(model_name: str) -> str:
    return "passage: " if "e5" in model_name.lower() else ""


def load_chunks() -> list[dict]:
    chunks: list[dict] = []
    with CHUNKS_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                chunks.append(json.loads(line))
    return chunks


def text_for_embedding(chunk: dict) -> str:
    """RFC-017: embed the child's embed_text (neighbor window) when present,
    falling back to `text`. chunks.jsonl is children-only (tools/chunker.py
    routes parent rows to parents.jsonl), so no kind_level filtering here."""
    return chunk.get("embed_text") or chunk.get("text") or ""


def write_meta(chunks: list[dict], path: Path) -> None:
    with path.open("w", encoding="utf-8") as f:
        for c in chunks:
            meta = {k: v for k, v in c.items() if k != "text"}
            f.write(json.dumps(meta, ensure_ascii=False) + "\n")


def read_meta(path: Path) -> list[dict]:
    metas: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                metas.append(json.loads(line))
    return metas


def read_existing_descriptor() -> dict | None:
    for src in (MANIFEST_PATH, PROGRESS_PATH):
        if src.exists():
            try:
                return json.loads(src.read_text())
            except Exception:
                continue
    return None


def archive_existing(reason: str) -> Path | None:
    """MOVE (never delete) existing embedding files into _archive/<model>-<ts>/."""
    present = [
        p for p in (EMB_PATH, META_PATH, MANIFEST_PATH, PROGRESS_PATH, PREINC_EMB, PREINC_META)
        if p.exists()
    ]
    if not present:
        return None
    desc = read_existing_descriptor() or {}
    label = (desc.get("model") or "unknown-model").replace("/", "_")
    rows = desc.get("rows_done", desc.get("chunk_count", "?"))
    dest = ARCHIVE_DIR / f"{label}-{time.strftime('%Y%m%dT%H%M%S')}"
    dest.mkdir(parents=True, exist_ok=True)
    for p in present:
        shutil.move(str(p), str(dest / p.name))
    (dest / "ARCHIVED.txt").write_text(
        f"Archived {time.strftime('%Y-%m-%dT%H:%M:%S')}\nreason: {reason}\n"
        f"model: {desc.get('model')}\nrows_done: {rows}\nchunk_count: {desc.get('chunk_count')}\n"
        f"dim: {desc.get('dim')}\n"
    )
    return dest


def snapshot_existing_for_resume() -> None:
    """Copy existing embeddings.npy + chunks_meta.jsonl to .preincremental.bak.* so
    a resume after crash can rebuild the id→vec map even if the active embeddings.npy
    has been overwritten by the new build."""
    if EMB_PATH.exists() and META_PATH.exists():
        if PREINC_EMB.exists():
            PREINC_EMB.unlink()
        if PREINC_META.exists():
            PREINC_META.unlink()
        shutil.copy2(EMB_PATH, PREINC_EMB)
        shutil.copy2(META_PATH, PREINC_META)


def cleanup_snapshot() -> None:
    for p in (PREINC_EMB, PREINC_META):
        if p.exists():
            p.unlink()


def build_id_to_vec(emb_path: Path, meta_path: Path, expected_dim: int | None) -> dict[str, np.ndarray]:
    """Read embeddings.npy + chunks_meta.jsonl and return {chunk_id: vector}.

    Returns {} if files are missing, misaligned, or dimensions don't match.
    """
    if not emb_path.exists() or not meta_path.exists():
        return {}
    try:
        emb = np.load(emb_path, mmap_mode="r")
    except Exception as e:
        print(f"  warning: could not load {emb_path.name}: {e}", file=sys.stderr)
        return {}
    if emb.ndim != 2:
        return {}
    if expected_dim is not None and emb.shape[1] != expected_dim:
        # Different model dim — can't reuse.
        return {}
    metas = read_meta(meta_path)
    if len(metas) != emb.shape[0]:
        print(
            f"  warning: meta count ({len(metas)}) != emb rows ({emb.shape[0]}); ignoring existing",
            file=sys.stderr,
        )
        return {}
    id_to_vec: dict[str, np.ndarray] = {}
    for row, meta in enumerate(metas):
        cid = meta.get("id")
        if cid:
            # Copy out of the memmap so we don't depend on the file after this point.
            id_to_vec[cid] = np.array(emb[row], dtype=np.float32, copy=True)
    return id_to_vec


def write_progress(model_name: str, rows_done: int, n_new: int, dim: int, batch_size: int, max_seq: int) -> None:
    """rows_done counts forward through the to-embed list (NEW chunks only), not all chunks."""
    PROGRESS_PATH.write_text(json.dumps({
        "model": model_name,
        "new_chunks_total": n_new,
        "new_chunks_done": rows_done,
        "dim": dim,
        "batch_size": batch_size,
        "max_seq_length": max_seq,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }, indent=2))


def manifest_complete(model_name: str, n: int) -> bool:
    if not (MANIFEST_PATH.exists() and EMB_PATH.exists()):
        return False
    try:
        mf = json.loads(MANIFEST_PATH.read_text())
        return bool(
            mf.get("model") == model_name
            and mf.get("chunk_count") == n
            and mf.get("complete") is True
        )
    except Exception:
        return False


def main() -> int:
    p = argparse.ArgumentParser(description="Embed corpus chunks with chunk_id-keyed carry-over (ADR-012).")
    p.add_argument("--model", default=DEFAULT_MODEL, help=f"HF model id (default: {DEFAULT_MODEL})")
    p.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    p.add_argument("--max-seq", type=int, default=DEFAULT_MAX_SEQ_LEN)
    p.add_argument("--flush-every", type=int, default=DEFAULT_FLUSH_EVERY)
    p.add_argument("--restart", action="store_true", help="Archive existing build and start fresh.")
    p.add_argument("--threads", type=int, default=None)
    args = p.parse_args()

    model_name = args.model
    prefix = passage_prefix(model_name)
    max_seq = model_seq_len(model_name, args.max_seq)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    chunks = load_chunks()
    n = len(chunks)
    print(f"Loaded {n:,} chunks from {CHUNKS_PATH.relative_to(REPO)}", file=sys.stderr)
    print(f"Model: {model_name}  |  max_seq={max_seq}  |  passage_prefix={prefix!r}", file=sys.stderr)

    if not args.restart and manifest_complete(model_name, n):
        # Vectors are unchanged (same model + count), but chunk METADATA may have been
        # edited (e.g. an author correction) with no change to text/ids. Row order is
        # deterministic and ids are stable, so refresh chunks_meta from chunks.jsonl
        # (cheap) rather than silently serving stale metadata. Only skip if it matches.
        existing_meta = read_meta(META_PATH) if META_PATH.exists() else []
        stripped = [{k: v for k, v in c.items() if k != "text"} for c in chunks]
        if existing_meta != stripped:
            write_meta(chunks, META_PATH)
            print("\n✓ Vectors unchanged; refreshed chunks_meta.jsonl from edited metadata.", file=sys.stderr)
        else:
            print("\n✓ Existing build for this model + chunk count matches — nothing to do.", file=sys.stderr)
        return 0

    # --- Decide source for the id→vec map (existing vs. snapshot for resume) ----
    desc = read_existing_descriptor()
    existing_dim = (desc or {}).get("dim")

    if args.restart:
        archived = archive_existing("--restart")
        if archived:
            print(f"  📦 Preserved existing embeddings → {archived.relative_to(REPO)}", file=sys.stderr)
        id_to_vec: dict[str, np.ndarray] = {}
        existing_dim = None
    elif desc and desc.get("model") and desc.get("model") != model_name:
        archived = archive_existing(f"model switch -> {model_name}")
        if archived:
            print(f"  📦 Preserved existing embeddings → {archived.relative_to(REPO)}", file=sys.stderr)
        id_to_vec = {}
        existing_dim = None
    else:
        # Prefer the active embeddings.npy + chunks_meta.jsonl. If a resume is in
        # progress, those have been (partially) overwritten — fall back to the
        # snapshot taken at the start of the prior run.
        progress = json.loads(PROGRESS_PATH.read_text()) if PROGRESS_PATH.exists() else None
        if progress and PREINC_EMB.exists() and PREINC_META.exists():
            print(
                f"  ↻ Resuming: rebuilding id→vec map from preincremental snapshot "
                f"({PREINC_EMB.name})",
                file=sys.stderr,
            )
            id_to_vec = build_id_to_vec(PREINC_EMB, PREINC_META, existing_dim)
        else:
            id_to_vec = build_id_to_vec(EMB_PATH, META_PATH, existing_dim)
        print(f"  Existing id→vec map: {len(id_to_vec):,} entries", file=sys.stderr)

    # --- Partition the new chunks into carry-over vs needs-encode ---------------
    carryover_rows: list[int] = []
    new_rows: list[int] = []
    for i, c in enumerate(chunks):
        cid = c.get("id")
        if cid and cid in id_to_vec:
            carryover_rows.append(i)
        else:
            new_rows.append(i)

    print(f"\n  Carry over: {len(carryover_rows):,} chunks (existing embeddings reused)", file=sys.stderr)
    print(f"  To encode:  {len(new_rows):,} chunks", file=sys.stderr)

    # --- Load the model ONLY if we have something to encode ---------------------
    dim: int
    model = None
    if new_rows:
        print(f"\nLoading model {model_name} ...", file=sys.stderr)
        print(f"  (first run downloads weights; subsequent runs use cache)", file=sys.stderr)
        import torch
        threads = args.threads or _THREADS
        torch.set_num_threads(threads)
        t0 = time.time()
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(model_name, trust_remote_code=True)
        model.max_seq_length = max_seq
        dim = model.get_sentence_embedding_dimension()
        print(f"  Model loaded in {time.time() - t0:.1f}s  |  dim={dim}  |  torch threads={threads}", file=sys.stderr)
        # Sanity: if we have existing embeddings, their dim must match the model's.
        if id_to_vec:
            sample = next(iter(id_to_vec.values()))
            if sample.shape[0] != dim:
                print(
                    f"  warning: existing dim {sample.shape[0]} != model dim {dim}; treating "
                    f"existing as unusable (archiving and starting fresh).",
                    file=sys.stderr,
                )
                archive_existing(f"dim mismatch: existing {sample.shape[0]} vs new {dim}")
                id_to_vec = {}
                # Re-partition: everything is now to-encode.
                carryover_rows = []
                new_rows = list(range(n))
    else:
        # Everything is carry-over; learn dim from any sample.
        if not id_to_vec:
            print("Nothing to embed AND no existing embeddings. Did the chunker write zero chunks?", file=sys.stderr)
            return 2
        sample = next(iter(id_to_vec.values()))
        dim = sample.shape[0]
        print(f"  All chunks already embedded ({dim}-dim). Skipping model load.", file=sys.stderr)

    # --- Snapshot existing files for resume safety, then write new ones ---------
    # We snapshot AFTER building id_to_vec (which loaded from the current files),
    # so the snapshot reflects what we just consumed. On resume, the snapshot lets
    # us rebuild id_to_vec even though the active EMB_PATH has been overwritten.
    snapshot_existing_for_resume()

    # Always (re)write meta first — cheap, order-stable, and a partial run still
    # has correct chunk attribution.
    write_meta(chunks, META_PATH)

    # Open (or re-open, on resume) the memmap-backed .npy.
    progress = json.loads(PROGRESS_PATH.read_text()) if PROGRESS_PATH.exists() else None
    resume_from = 0
    if progress and progress.get("new_chunks_total") == len(new_rows) and EMB_PATH.exists():
        # Resume: open existing file and pick up where we left off in the new_rows list.
        try:
            emb = np.lib.format.open_memmap(EMB_PATH, mode="r+")
            if emb.shape == (n, dim):
                resume_from = int(progress.get("new_chunks_done", 0))
                print(f"  ↻ Resuming new-chunk encode from {resume_from:,}/{len(new_rows):,}", file=sys.stderr)
            else:
                emb = np.lib.format.open_memmap(EMB_PATH, mode="w+", dtype=np.float32, shape=(n, dim))
        except Exception:
            emb = np.lib.format.open_memmap(EMB_PATH, mode="w+", dtype=np.float32, shape=(n, dim))
    else:
        emb = np.lib.format.open_memmap(EMB_PATH, mode="w+", dtype=np.float32, shape=(n, dim))

    # --- Copy carry-over vectors into their new positions -----------------------
    # (Always re-do this; cheap, idempotent.)
    if id_to_vec and carryover_rows:
        t0 = time.time()
        for row in carryover_rows:
            cid = chunks[row]["id"]
            emb[row] = id_to_vec[cid]
        emb.flush()
        print(
            f"  ✓ Copied {len(carryover_rows):,} carry-over embeddings into new rows "
            f"({time.time() - t0:.1f}s).",
            file=sys.stderr,
        )

    # Release the in-RAM dict now that we've placed everything (frees ~28 MB for 7k chunks).
    id_to_vec.clear()

    # --- Encode the new chunks --------------------------------------------------
    if new_rows and resume_from < len(new_rows):
        prefix = passage_prefix(model_name)
        # Build the text list and corresponding corpus rows in lockstep.
        to_embed_texts = [prefix + text_for_embedding(chunks[r]) for r in new_rows]

        bs = args.batch_size
        n_new = len(new_rows)
        try:
            from tqdm import tqdm
            bar = tqdm(
                total=n_new, initial=resume_from, unit="chunk", dynamic_ncols=True,
                smoothing=0.1, file=sys.stderr, desc="Encoding NEW",
            )
            use_bar = True
        except Exception:
            bar = None
            use_bar = False

        t_start = time.time()
        batches_since_flush = 0
        i = resume_from
        try:
            while i < n_new:
                j = min(i + bs, n_new)
                vecs = model.encode(  # type: ignore[union-attr]
                    to_embed_texts[i:j],
                    batch_size=bs,
                    convert_to_numpy=True,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                ).astype(np.float32)
                for k, vec in enumerate(vecs):
                    corpus_row = new_rows[i + k]
                    emb[corpus_row] = vec
                i = j
                batches_since_flush += 1

                if batches_since_flush >= args.flush_every or i >= n_new:
                    emb.flush()
                    write_progress(model_name, i, n_new, dim, bs, max_seq)
                    batches_since_flush = 0

                done = i - resume_from
                rate = done / max(time.time() - t_start, 1e-6)
                remaining = (n_new - i) / max(rate, 1e-6)
                if use_bar:
                    bar.set_postfix_str(f"{rate:.2f}/s  ETA {remaining/60:.1f}m")
                    bar.n = i
                    bar.refresh()
                else:
                    print(
                        f"  {i:,}/{n_new:,} ({100*i/n_new:.1f}%)  {rate:.2f}/s  ETA {remaining/60:.1f}m",
                        file=sys.stderr,
                    )
        except KeyboardInterrupt:
            emb.flush()
            write_progress(model_name, i, n_new, dim, bs, max_seq)
            if use_bar and bar:
                bar.close()
            print(
                f"\n⏸  Interrupted at new-chunk {i:,}/{n_new:,}. Progress saved — re-run to resume.",
                file=sys.stderr,
            )
            return 130

        if use_bar and bar:
            bar.n = n_new
            bar.close()
        emb.flush()

    # --- Finalize ---------------------------------------------------------------
    manifest = {
        "model": model_name,
        "dim": int(dim),
        "chunk_count": n,
        "normalized": True,
        "max_seq_length": max_seq,
        "complete": True,
        "carryover_chunks": len(carryover_rows),
        "new_chunks": len(new_rows),
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))
    if PROGRESS_PATH.exists():
        PROGRESS_PATH.unlink()
    cleanup_snapshot()

    print(
        f"\n✓ Done. Total {n:,} embeddings ({len(carryover_rows):,} carry-over, {len(new_rows):,} new).",
        file=sys.stderr,
    )
    print(f"  {EMB_PATH.relative_to(REPO)}  ({EMB_PATH.stat().st_size/1024/1024:.1f} MB)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
