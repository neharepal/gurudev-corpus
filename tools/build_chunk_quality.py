"""One-time (idempotent) pass: add `quality_score` to each chunks_meta row.

Reads chunk text from 04_processed/chunks.jsonl (row-aligned) and the metadata
from 04_processed/embeddings/chunks_meta.jsonl, writes quality_score into each
meta row. Does NOT touch embeddings.npy — no re-embed. Atomic write via temp+replace.
"""
from __future__ import annotations
import json, os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chunk_quality

REPO = Path(__file__).resolve().parent.parent
META_PATH = REPO / "04_processed" / "embeddings" / "chunks_meta.jsonl"
CHUNKS_PATH = REPO / "04_processed" / "chunks.jsonl"


def _load_texts(chunks_path: Path) -> list[str]:
    texts: list[str] = []
    with chunks_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                texts.append(json.loads(line).get("text", ""))
            except Exception:
                texts.append("")
    return texts


def build_quality(meta_path: Path, chunks_path: Path) -> int:
    texts = _load_texts(chunks_path)
    rows: list[dict] = []
    with meta_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    if len(texts) != len(rows):
        raise ValueError(
            f"chunks.jsonl ({len(texts)}) and chunks_meta.jsonl ({len(rows)}) "
            f"line counts differ — cannot align quality_score safely."
        )
    updated = 0
    for i, row in enumerate(rows):
        text = texts[i] if i < len(texts) else ""
        row["quality_score"] = chunk_quality.quality_score(text)
        updated += 1
    tmp = meta_path.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    os.replace(tmp, meta_path)
    return updated


if __name__ == "__main__":
    n = build_quality(META_PATH, CHUNKS_PATH)
    print(f"quality_score written for {n} chunks -> {META_PATH}")
