#!/usr/bin/env python3
"""
Corpus chunker — text → chunks.jsonl

Walks the corpus, reads every text source, splits into ~500-token chunks
that respect paragraph boundaries, propagates metadata, and emits one
JSON line per chunk at 04_processed/chunks.jsonl.

Per RFC-003 §Chunking:
  - Target ~500 tokens (~2000 chars); allow up to 700 (~2800 chars).
  - Never split mid-paragraph; prefer section-heading boundaries.
  - 50-token overlap (~200 chars) between adjacent chunks.
  - Marathi verses + meanings stay together (skip force-split if mostly Devanagari).
  - Frontmatter is stripped from chunk content but its fields propagate as metadata.

Per ADR-008: no story aggregation. Athvani sources read from variant files
*and* from raw .docx files in athvani folders (via pandoc on-the-fly).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterator

import yaml

REPO = Path(__file__).resolve().parent.parent
OUT_PATH = REPO / "04_processed" / "chunks.jsonl"


def _sorted_dir(p: Path):
    """Sort directory entries by name for deterministic scan order.

    Filesystem iterdir() order is implementation-dependent (APFS uses
    insertion order, ext4 is hashed, etc.). Sorting by name makes
    chunks.jsonl reproducible bit-for-bit across machines and across
    runs. Critical for the chunk_id-keyed embedding scheme (ADR-012):
    embeddings carry over by chunk_id, not row index, but stable order
    also keeps `chunks_meta.jsonl` diffs minimal.
    """
    return sorted(p.iterdir(), key=lambda x: x.name)

# Token estimation constants. We avoid tiktoken to keep deps minimal.
# Rule of thumb: 1 token ≈ 4 chars for English, ≈ 3 chars for Devanagari.
# A char-based target is good enough for chunking-boundary decisions.
TARGET_CHARS = 2000      # ~500 tokens
MAX_CHARS = 2800         # ~700 tokens — hard cap
OVERLAP_CHARS = 200      # ~50 tokens between chunks

# Paths to scan for canonical & aggregated content.
CANONICAL_ROOT = REPO / "01_canonical"
ATHVANI_ROOT = REPO / "02_aggregated" / "athvani"
BIOGRAPHY_ROOT = REPO / "02_aggregated" / "biography"
PERIODICALS_ROOT = REPO / "02_aggregated" / "periodicals"
REFERENCE_ROOT = REPO / "03_catalog" / "reference"

# Original athvani docx folders in 00_raw (read-only); we extract on the fly.
# Per ADR-005, these are still in staging — we don't move them, we just read.
RAW_ATHVANI_FOLDERS = [
    ("00_raw/drive_dump_2026-06-11/Neha/श्री गुरुदेवांच्या आठवणी", "gurudev_ranade"),
    ("00_raw/drive_dump_2026-06-11/Neha/गुरुदेवांच्या आठवणी", "gurudev_ranade"),
    ("00_raw/drive_dump_2026-06-11/Neha/श्रीभाऊसाहेब महाराजांच्या आठवणी", "bhausaheb_maharaj"),
    ("00_raw/drive_dump_2026-06-11/Neha/श्रीअंबुराव महाराज यांच्या आठवणी", "amburao_maharaj"),
    ("00_raw/drive_dump_2026-06-11/Neha/निम्बर्गी महाराज आठवणी", "nimbargi_maharaj"),
    ("00_raw/drive_dump_2026-06-11/Neha/बाबांच्या आठवणी", "other_devotees"),
    ("00_raw/drive_dump_2026-06-11/Neha/साधूबुवांच्या आठवणी.", "other_devotees"),
    ("00_raw/neha-initial-download-2026-07-08", "gurudev_ranade"),
]

# Raw athvani docx filenames to skip (already ingested as separate canonical works).
RAW_ATHVANI_SKIP_FILES = {
    "श्री न. ग. दामले यांचे प्रवचन.docx",  # already ingested as n-g-damle-pravachan
}


# ---------------------------------------------------------------------------
# Frontmatter / yaml helpers
# ---------------------------------------------------------------------------
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def split_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, body) for a markdown file with optional YAML frontmatter."""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except Exception:
        fm = {}
    body = text[m.end():]
    return fm, body


def load_meta(work_dir: Path) -> dict:
    """Load meta.yaml from a work folder (one level above the language dir)."""
    p = work_dir / "meta.yaml"
    if not p.exists():
        return {}
    try:
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Pandoc helper for on-the-fly DOCX extraction
# ---------------------------------------------------------------------------
def docx_to_markdown(src: Path) -> str:
    """Extract clean markdown from a docx; returns empty string on failure."""
    candidates = [
        "pandoc",
        "/opt/homebrew/bin/pandoc",
        "/Users/neharepal/opt/anaconda3/bin/pandoc",
    ]
    for cand in candidates:
        try:
            r = subprocess.run(
                [cand, "-f", "docx", "-t", "markdown_strict", "--wrap=none", str(src)],
                capture_output=True, text=True, timeout=120,
            )
            if r.returncode == 0:
                return clean_pandoc(r.stdout)
        except FileNotFoundError:
            continue
        except Exception:
            return ""
    return ""


def clean_pandoc(text: str) -> str:
    """Strip pandoc escape sequences and collapse excess blank lines."""
    text = text.replace("\\*", "*").replace("\\'", "'").replace('\\"', '"')
    text = text.replace("\\[", "[").replace("\\]", "]").replace("\\_", "_")
    text = text.replace("\\#", "#").replace("\\-", "-").replace("\\.", ".")
    text = text.replace("\\(", "(").replace("\\)", ")").replace("\\|", "|")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Chunk splitter
# ---------------------------------------------------------------------------
PARA_SPLIT_RE = re.compile(r"\n\s*\n")
DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]")
SENTENCE_END_RE = re.compile(r"(?<=[.!?।])\s+")


def is_mostly_devanagari(text: str, threshold: float = 0.3) -> bool:
    if not text:
        return False
    deva = len(DEVANAGARI_RE.findall(text))
    return deva / max(len(text), 1) > threshold


def force_split_long_paragraph(para: str, target: int) -> list[str]:
    """Force-split a paragraph longer than target. Use sentence boundaries when possible."""
    if is_mostly_devanagari(para):
        # Don't split Devanagari verse/meaning blocks aggressively.
        # Allow up to 1.5x target if mostly Devanagari (verses + meanings belong together).
        if len(para) <= int(target * 1.6):
            return [para]
    # Split on sentence boundaries.
    sentences = SENTENCE_END_RE.split(para)
    pieces: list[str] = []
    buf = ""
    for s in sentences:
        if buf and len(buf) + len(s) + 1 > target:
            pieces.append(buf.strip())
            buf = s
        else:
            buf = (buf + " " + s) if buf else s
    if buf.strip():
        pieces.append(buf.strip())
    return pieces or [para]


def chunk_text(text: str) -> list[dict]:
    """Split text into chunk dicts: {text, char_start, char_end}.

    Strategy:
      - Split into paragraphs.
      - Greedy-pack paragraphs into a chunk until adding the next would exceed TARGET_CHARS.
      - Hard-cap chunks at MAX_CHARS — force-split a paragraph if needed.
      - Between adjacent chunks, prepend the trailing OVERLAP_CHARS of the previous chunk
        (truncated to whole-paragraph boundary when possible) for context preservation.
    """
    paragraphs = [p.strip() for p in PARA_SPLIT_RE.split(text) if p.strip()]
    if not paragraphs:
        return []

    chunks: list[dict] = []
    char_pos = 0

    cur: list[str] = []
    cur_len = 0

    def emit_chunk(parts: list[str], start: int) -> None:
        body = "\n\n".join(parts).strip()
        if not body:
            return
        end = start + len(body)
        chunks.append({"text": body, "char_start": start, "char_end": end})

    for p in paragraphs:
        if len(p) > MAX_CHARS:
            # First flush whatever's in cur, then split this big paragraph.
            if cur:
                emit_chunk(cur, char_pos)
                char_pos += cur_len + 2
                cur, cur_len = [], 0
            for piece in force_split_long_paragraph(p, TARGET_CHARS):
                emit_chunk([piece], char_pos)
                char_pos += len(piece) + 2
            continue

        # If adding this paragraph would overflow target, close current chunk first.
        if cur and cur_len + len(p) + 2 > TARGET_CHARS:
            emit_chunk(cur, char_pos)
            char_pos += cur_len + 2
            # Start the next chunk with overlap from the tail of current.
            tail = ""
            if OVERLAP_CHARS > 0 and chunks:
                last = chunks[-1]["text"]
                tail = last[-OVERLAP_CHARS:]
                tail_para_boundary = tail.find("\n\n")
                if tail_para_boundary > 0:
                    tail = tail[tail_para_boundary + 2:]
            cur = [tail.strip()] if tail.strip() else []
            cur_len = sum(len(x) for x in cur) + 2 * (len(cur) - 1 if len(cur) > 1 else 0)

        cur.append(p)
        cur_len = sum(len(x) for x in cur) + 2 * (len(cur) - 1)

    if cur:
        emit_chunk(cur, char_pos)

    return chunks


def estimate_tokens(text: str) -> int:
    """Rough token estimate: char-based, with Devanagari getting a slightly higher density."""
    if is_mostly_devanagari(text):
        return max(1, len(text) // 3)
    return max(1, len(text) // 4)


# ---------------------------------------------------------------------------
# Source enumeration
# ---------------------------------------------------------------------------
def emit_chunks_for_source(
    source_path: Path,
    body_text: str,
    base_meta: dict,
) -> Iterator[dict]:
    """Yield chunk dicts for a single text source, merging base_meta + chunk-local fields."""
    chunks = chunk_text(body_text)
    total = len(chunks)
    work_id = base_meta.get("work_id") or base_meta.get("id") or source_path.stem
    for i, c in enumerate(chunks):
        chunk = dict(base_meta)
        chunk["chunk_index"] = i
        chunk["chunk_total"] = total
        chunk["char_start"] = c["char_start"]
        chunk["char_end"] = c["char_end"]
        chunk["text"] = c["text"]
        chunk["token_estimate"] = estimate_tokens(c["text"])
        chunk["id"] = f"{work_id}--{base_meta.get('language', 'unk')}--{i:04d}"
        chunk["source_path"] = str(source_path.relative_to(REPO))
        yield chunk


def scan_canonical_text_md() -> Iterator[dict]:
    """For every text.md under 01_canonical/<author>/<type>/<work>/<lang>/."""
    for author_dir in (_sorted_dir(CANONICAL_ROOT) if CANONICAL_ROOT.exists() else []):
        if not author_dir.is_dir():
            continue
        author = author_dir.name
        for type_dir in _sorted_dir(author_dir):
            if not type_dir.is_dir():
                continue
            work_type = type_dir.name  # books | lectures | letters
            for work_dir in _sorted_dir(type_dir):
                if not work_dir.is_dir():
                    continue
                work_meta = load_meta(work_dir)
                for lang_dir in _sorted_dir(work_dir):
                    if not lang_dir.is_dir():
                        continue
                    text_md = lang_dir / "text.md"
                    if not text_md.exists():
                        continue
                    raw = text_md.read_text(encoding="utf-8", errors="replace")
                    fm, body = split_frontmatter(raw)
                    base = {
                        "kind": "canonical",
                        "author": author,
                        "work_type": work_type,
                        "work_id": fm.get("work_id") or work_meta.get("id") or work_dir.name,
                        "title": fm.get("title_en") or work_meta.get("title_en") or work_meta.get("title") or work_dir.name,
                        "language": fm.get("language") or lang_dir.name,
                        "tags": work_meta.get("tags") or [],
                    }
                    yield from emit_chunks_for_source(text_md, body, base)


def scan_biography() -> Iterator[dict]:
    for about_dir in (_sorted_dir(BIOGRAPHY_ROOT) if BIOGRAPHY_ROOT.exists() else []):
        if not about_dir.is_dir() or not about_dir.name.startswith("about_"):
            continue
        member = about_dir.name[len("about_"):]
        for work_dir in _sorted_dir(about_dir):
            if not work_dir.is_dir():
                continue
            work_meta = load_meta(work_dir)
            for lang_dir in _sorted_dir(work_dir):
                if not lang_dir.is_dir():
                    continue
                text_md = lang_dir / "text.md"
                if not text_md.exists():
                    continue
                raw = text_md.read_text(encoding="utf-8", errors="replace")
                fm, body = split_frontmatter(raw)
                base = {
                    "kind": "biography",
                    "about_member": member,
                    "work_id": fm.get("work_id") or work_meta.get("id") or work_dir.name,
                    "title": fm.get("title_en") or work_meta.get("title_en") or work_meta.get("title") or work_dir.name,
                    "language": fm.get("language") or lang_dir.name,
                    "tags": work_meta.get("tags") or [],
                }
                yield from emit_chunks_for_source(text_md, body, base)


def scan_athvani_variants() -> Iterator[dict]:
    """Variants under .../stories/<story>/<lang>/variants/*.md (including the seed)."""
    if not ATHVANI_ROOT.exists():
        return
    for about_dir in _sorted_dir(ATHVANI_ROOT):
        if not about_dir.is_dir() or not about_dir.name.startswith("about_"):
            continue
        member = about_dir.name[len("about_"):]
        stories_dir = about_dir / "stories"
        if not stories_dir.exists():
            continue
        for story_dir in _sorted_dir(stories_dir):
            if not story_dir.is_dir():
                continue
            story_meta = load_meta(story_dir)
            for lang_dir in _sorted_dir(story_dir):
                if not lang_dir.is_dir():
                    continue
                variants_dir = lang_dir / "variants"
                if not variants_dir.exists():
                    continue
                for vfile in _sorted_dir(variants_dir):
                    if not vfile.is_file() or vfile.suffix != ".md":
                        continue
                    raw = vfile.read_text(encoding="utf-8", errors="replace")
                    fm, body = split_frontmatter(raw)
                    base = {
                        "kind": "athvani",
                        "about_member": member,
                        "work_id": fm.get("source_work") or story_meta.get("id") or story_dir.name,
                        "story_id": story_dir.name,
                        "title": story_meta.get("title_en") or story_meta.get("title") or story_dir.name,
                        "narrator": fm.get("narrator") or "",
                        "source_work": fm.get("source_work") or "",
                        "compiler": fm.get("compiler") or "",
                        "language": fm.get("language") or lang_dir.name,
                    }
                    yield from emit_chunks_for_source(vfile, body, base)


def scan_athvani_raw() -> Iterator[dict]:
    """Read every raw athvani docx (in 00_raw athvani folders + 02_aggregated raw)."""
    visited: set[Path] = set()

    # 00_raw athvani folders.
    for folder_rel, member in RAW_ATHVANI_FOLDERS:
        folder = REPO / folder_rel
        if not folder.exists():
            continue
        for f in sorted(folder.iterdir()):
            if not f.is_file() or f.suffix.lower() != ".docx":
                continue
            if f.name in RAW_ATHVANI_SKIP_FILES:
                continue
            visited.add(f.resolve())
            yield from _emit_raw_athvani(f, member)

    # 02_aggregated/athvani/<member>/raw/ — dashboard-categorized files.
    if ATHVANI_ROOT.exists():
        for about_dir in _sorted_dir(ATHVANI_ROOT):
            if not about_dir.is_dir() or not about_dir.name.startswith("about_"):
                continue
            member = about_dir.name[len("about_"):]
            raw_dir = about_dir / "raw"
            if not raw_dir.exists():
                continue
            for f in sorted(raw_dir.iterdir()):
                if not f.is_file() or f.suffix.lower() != ".docx":
                    continue
                if f.resolve() in visited:
                    continue
                visited.add(f.resolve())
                yield from _emit_raw_athvani(f, member)


def _emit_raw_athvani(docx_path: Path, member: str) -> Iterator[dict]:
    md = docx_to_markdown(docx_path)
    if not md or len(md.strip()) < 100:
        return
    # Use basename as work_id slug.
    slug = re.sub(r"[^A-Za-z0-9ऀ-ॿ]+", "-", docx_path.stem).strip("-").lower()[:80]
    base = {
        "kind": "athvani",
        "about_member": member,
        "work_id": slug,
        "title": docx_path.stem,
        "narrator": "",
        "source_work": docx_path.name,
        "language": "mr",
        "from_raw_docx": True,
    }
    yield from emit_chunks_for_source(docx_path, md, base)


def scan_periodicals() -> Iterator[dict]:
    for work_dir in (_sorted_dir(PERIODICALS_ROOT) if PERIODICALS_ROOT.exists() else []):
        if not work_dir.is_dir():
            continue
        work_meta = load_meta(work_dir)
        for lang_dir in _sorted_dir(work_dir):
            if not lang_dir.is_dir():
                continue
            text_md = lang_dir / "text.md"
            if not text_md.exists():
                continue
            raw = text_md.read_text(encoding="utf-8", errors="replace")
            fm, body = split_frontmatter(raw)
            base = {
                "kind": "periodical",
                "work_id": fm.get("work_id") or work_meta.get("id") or work_dir.name,
                "title": fm.get("title_en") or work_meta.get("title_en") or work_dir.name,
                "language": fm.get("language") or lang_dir.name,
            }
            yield from emit_chunks_for_source(text_md, body, base)


def scan_reference() -> Iterator[dict]:
    """Reference content gets a low-weight tag — retrieval shouldn't lean on it."""
    for work_dir in (_sorted_dir(REFERENCE_ROOT) if REFERENCE_ROOT.exists() else []):
        if not work_dir.is_dir():
            continue
        work_meta = load_meta(work_dir)
        for lang_dir in _sorted_dir(work_dir):
            if not lang_dir.is_dir():
                continue
            text_md = lang_dir / "text.md"
            if not text_md.exists():
                continue
            raw = text_md.read_text(encoding="utf-8", errors="replace")
            fm, body = split_frontmatter(raw)
            base = {
                "kind": "reference",
                "retrieval_weight": "low",
                "work_id": fm.get("work_id") or work_meta.get("id") or work_dir.name,
                "title": fm.get("title_en") or work_meta.get("title_en") or work_dir.name,
                "language": fm.get("language") or lang_dir.name,
            }
            yield from emit_chunks_for_source(text_md, body, base)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    by_kind: dict[str, int] = {}
    by_lang: dict[str, int] = {}
    total_tokens = 0

    print("Scanning corpus and chunking...", file=sys.stderr)
    with OUT_PATH.open("w", encoding="utf-8") as out:
        for scan_fn, label in [
            (scan_canonical_text_md, "canonical"),
            (scan_biography, "biography"),
            (scan_athvani_variants, "athvani-variants"),
            (scan_athvani_raw, "athvani-raw"),
            (scan_periodicals, "periodicals"),
            (scan_reference, "reference"),
        ]:
            count = 0
            for chunk in scan_fn():
                out.write(json.dumps(chunk, ensure_ascii=False) + "\n")
                total += 1
                count += 1
                k = chunk.get("kind", "?")
                lang = chunk.get("language", "?")
                by_kind[k] = by_kind.get(k, 0) + 1
                by_lang[lang] = by_lang.get(lang, 0) + 1
                total_tokens += chunk.get("token_estimate", 0)
            print(f"  {label}: {count} chunks", file=sys.stderr)

    print(f"\n✓ Wrote {total:,} chunks to {OUT_PATH.relative_to(REPO)}", file=sys.stderr)
    print(f"  Size: {OUT_PATH.stat().st_size / 1024 / 1024:.1f} MB", file=sys.stderr)
    print(f"  Estimated total tokens: {total_tokens:,}", file=sys.stderr)
    print(f"\n  By kind:", file=sys.stderr)
    for k, c in sorted(by_kind.items(), key=lambda x: -x[1]):
        print(f"    {k}: {c:,}", file=sys.stderr)
    print(f"  By language:", file=sys.stderr)
    for lang, c in sorted(by_lang.items(), key=lambda x: -x[1]):
        print(f"    {lang}: {c:,}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
