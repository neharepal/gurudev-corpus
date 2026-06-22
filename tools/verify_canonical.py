#!/usr/bin/env python3
"""
verify_canonical.py — compare a canonical book in our corpus against the
Internet Archive OCR of the same work, find passages that diverge.

Why this exists
---------------
Our canonical books were typed by hand into .docx files (see meta.yaml's
`extracted_via`). Transcription errors are possible — dropped lines,
misread words, sentence reorderings — and any such error becomes a
"verbatim quote" attributed to Gurudev on the page. ADR-007 promises
verbatim quotes; we have to keep that promise.

IA holds OCR'd PDFs of (most of) Gurudev's published books. OCR text is
noisy at the character level but reliable at the sentence level — it's
the only second source we have. Comparing our typed transcript against
the IA OCR finds:

  - Where we are aligned (high-confidence verbatim text)
  - Where we differ AND IA has clean text → likely OUR transcription error
  - Where we differ AND IA has gibberish → likely OCR noise, not our error
  - Where one source has content the other lacks → edition difference OR
    skipped material

Strategy
--------
1. Download IA djvu text once, cache locally.
2. Normalize both sides: lowercase, strip non-alphanumeric except spaces,
   collapse whitespace, drop empty lines.
3. Tokenize into word streams.
4. SequenceMatcher.get_matching_blocks() to align.
5. Report:
   - Overall match ratio
   - The longest divergence regions (with context from each side)
   - Words/blocks our text has that IA does not (potential additions or
     transcription errors that introduce new words)
   - Words/blocks IA has that our text does not (potential omissions in
     our transcript, OR genuine OCR garbage)

Usage
-----
    python3 tools/verify_canonical.py <book-path> <ia-identifier>

Example
-------
    python3 tools/verify_canonical.py \\
        01_canonical/gurudev_ranade/books/pathway-to-god-in-hindi-literature \\
        pathway-to-god-in-hindi-literature

Output goes to stdout (use `tee` to save). Cache lives in
`04_processed/ia_cache/`.
"""

from __future__ import annotations

import difflib
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
IA_CACHE = REPO / "04_processed" / "ia_cache"


# ---------- Acquisition ----------

def find_djvu_filename(ia_id: str) -> str:
    """List IA files and return the djvu.txt filename (preserves casing)."""
    import json
    meta_url = f"https://archive.org/metadata/{ia_id}"
    with urllib.request.urlopen(meta_url, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    for f in data.get("files", []):
        name = f.get("name", "")
        if name.lower().endswith("_djvu.txt"):
            return name
    raise RuntimeError(f"No djvu.txt found in IA item {ia_id}")


def fetch_ia_text(ia_id: str) -> str:
    """Download (and cache) the IA djvu OCR text for `ia_id`."""
    IA_CACHE.mkdir(parents=True, exist_ok=True)
    cache_path = IA_CACHE / f"{ia_id}.txt"
    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8", errors="replace")
    djvu_name = find_djvu_filename(ia_id)
    url = (
        f"https://archive.org/download/{ia_id}/"
        + urllib.parse.quote(djvu_name)
    )
    print(f"[fetch] {url}", file=sys.stderr)
    with urllib.request.urlopen(url, timeout=120) as resp:
        text = resp.read().decode("utf-8", errors="replace")
    cache_path.write_text(text, encoding="utf-8")
    return text


def load_corpus_text(book_dir: Path) -> str:
    """Concatenate every text.md under the book directory (en + mr if both)."""
    md_files = sorted(book_dir.rglob("text.md"))
    if not md_files:
        raise RuntimeError(f"No text.md under {book_dir}")
    parts: list[str] = []
    for p in md_files:
        parts.append(p.read_text(encoding="utf-8", errors="replace"))
    return "\n\n".join(parts)


# ---------- Normalization ----------

_FRONTMATTER = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)
_WS = re.compile(r"\s+")
# Strip everything except lowercase alphanumerics + whitespace. Apostrophes
# and smart quotes are dropped so "mystic's" / "mystic s" / "mystics" all
# normalize to "mystics" and don't false-positive as text differences.
_NON_ALPHA = re.compile(r"[^a-z0-9\s]")


def strip_frontmatter(md: str) -> str:
    return _FRONTMATTER.sub("", md, count=1)


def normalize_words(s: str) -> list[str]:
    """Lowercase → strip non-alpha → word list."""
    s = s.lower()
    s = _NON_ALPHA.sub(" ", s)
    s = _WS.sub(" ", s).strip()
    return s.split()


# ---------- Alignment + reporting ----------

def alignment_stats(corpus_words: list[str], ia_words: list[str]) -> dict:
    sm = difflib.SequenceMatcher(a=corpus_words, b=ia_words, autojunk=False)
    blocks = sm.get_matching_blocks()
    aligned = sum(b.size for b in blocks)
    return {
        "corpus_words": len(corpus_words),
        "ia_words": len(ia_words),
        "aligned_words": aligned,
        "ratio": sm.ratio(),
        "blocks": blocks,
    }


def top_divergences(
    corpus_words: list[str],
    ia_words: list[str],
    blocks: list[difflib.Match],
    top_n: int = 10,
) -> list[tuple[int, str, str]]:
    """
    Walk the matching blocks; the gaps between them are the divergences.
    Return the top-N largest divergence regions as (size, our_snippet,
    ia_snippet) tuples, sorted by combined gap size.
    """
    gaps: list[tuple[int, str, str]] = []
    a_prev = 0
    b_prev = 0
    for blk in blocks:
        a_gap = corpus_words[a_prev : blk.a]
        b_gap = ia_words[b_prev : blk.b]
        if a_gap or b_gap:
            size = len(a_gap) + len(b_gap)
            gaps.append((size, " ".join(a_gap), " ".join(b_gap)))
        a_prev = blk.a + blk.size
        b_prev = blk.b + blk.size
    gaps.sort(key=lambda g: -g[0])
    return gaps[:top_n]


def truncate(s: str, n: int = 220) -> str:
    if len(s) <= n:
        return s
    return s[: n - 1] + "…"


# ---------- Small-gap audit (the actual transcription concern) ----------

def looks_like_ocr_noise(words: list[str]) -> bool:
    """OCR'd Devanagari turns into runs of 1–3 char Latin gibberish after
    normalization (`at ail ait aft ar`). Flag when >60% of words are
    that short."""
    if not words:
        return False
    short = sum(1 for w in words if len(w) <= 3)
    return short / len(words) > 0.6


def looks_like_index_entries(words: list[str]) -> bool:
    """Index lines after normalization are dense with bare page numbers
    (`p 245 pp 320 351 245 262`). Flag when >30% are digits-only."""
    if not words:
        return False
    nums = sum(1 for w in words if w.isdigit())
    return nums / len(words) > 0.3


# Running headers / footers in the IA scan look like this after normalization:
#   pathway togod h l parti
#   pathway to god h l part i
#   chap v highest ascent 215
#   chap ii moral preparation 295
# Detect by checking for a small set of tokens that appear in nearly every
# such header.
_HEADER_TOKENS = {
    "pathway",
    "togod",
    "god",
    "chap",
    "chapter",
    "moral",
    "preparation",
    "highest",
    "ascent",
    "h",
    "l",
    "part",
    "parti",
    "partl",
    "partll",
    "partli",
    "partlii",
    "parrl",
    "parrit",
    "parri",
    "pari",
    "i",
    "ii",
    "iii",
    "iv",
    "v",
    "vi",
}


def looks_like_page_header(words: list[str]) -> bool:
    """A running page or chapter header from the IA scan. These have at
    least 3 tokens from the small header vocabulary above, often plus a
    page number."""
    if not words:
        return False
    hits = sum(1 for w in words if w in _HEADER_TOKENS)
    return hits >= 3 or hits / len(words) > 0.5


def small_gap_audit(
    corpus_words: list[str],
    ia_words: list[str],
    blocks: list[difflib.Match],
    *,
    max_gap_words: int = 40,
    min_anchor_words: int = 30,
) -> list[dict]:
    """
    Walk matching blocks and surface gaps that look like real transcription
    differences — small word-stream divergences embedded inside two
    well-aligned anchor passages.

    Returns a list of dicts. Each dict carries the gap, its size on each
    side, the surrounding anchor context, and a heuristic category.
    """
    out: list[dict] = []
    blocks = list(blocks)
    for i in range(1, len(blocks)):
        prev = blocks[i - 1]
        curr = blocks[i]
        # Gap = the region between two aligned blocks.
        a_lo, a_hi = prev.a + prev.size, curr.a
        b_lo, b_hi = prev.b + prev.size, curr.b
        a_gap = corpus_words[a_lo:a_hi]
        b_gap = ia_words[b_lo:b_hi]

        # Both gaps empty (perfectly contiguous match) — nothing to report.
        if not a_gap and not b_gap:
            continue

        # Skip gaps where the surrounding anchors are too short. Short
        # anchors mean we're in unaligned / front-matter territory, so the
        # "gap" isn't a meaningful diff against context.
        if (
            prev.size < min_anchor_words
            or curr.size < min_anchor_words
        ):
            continue

        # Skip gaps that are too large — those are edition-level
        # differences (chapters added/dropped, addenda, indices).
        if len(a_gap) > max_gap_words or len(b_gap) > max_gap_words:
            continue

        # Skip Devanagari OCR noise on the IA side.
        if looks_like_ocr_noise(b_gap):
            continue

        # Skip index-entry-like gaps on either side.
        if looks_like_index_entries(a_gap) or looks_like_index_entries(b_gap):
            continue

        # Skip IA running page/chapter headers that leak into the gap.
        if looks_like_page_header(b_gap):
            continue

        # Skip OCR word-splitting: when one side joined-without-spaces is
        # a substring of the other joined-without-spaces, the two sides
        # agree on letters — they just disagree on word boundaries.
        # Common in IA when a word wraps at a line break (`quieti stic`).
        a_joined = "".join(a_gap)
        b_joined = "".join(b_gap)
        if a_joined and b_joined:
            if a_joined in b_joined or b_joined in a_joined:
                continue

        # Surrounding context for human review.
        anchor_before = " ".join(corpus_words[max(0, prev.a + prev.size - 8) : prev.a + prev.size])
        anchor_after = " ".join(corpus_words[curr.a : curr.a + 8])

        if not a_gap and b_gap:
            cat = "ours-missing"   # IA has it, we don't
        elif a_gap and not b_gap:
            cat = "ours-extra"     # We have it, IA doesn't
        else:
            cat = "text-diff"      # Both sides have it but they differ

        out.append({
            "category": cat,
            "size": len(a_gap) + len(b_gap),
            "anchor_before": anchor_before,
            "ours": " ".join(a_gap),
            "ia": " ".join(b_gap),
            "anchor_after": anchor_after,
        })

    return out


# ---------- Main ----------

def main() -> int:
    if len(sys.argv) != 3:
        print(
            "Usage: verify_canonical.py <book-path-from-repo> <ia-identifier>",
            file=sys.stderr,
        )
        return 2

    book_path = REPO / sys.argv[1]
    ia_id = sys.argv[2]

    if not book_path.exists():
        print(f"Not found: {book_path}", file=sys.stderr)
        return 2

    print(f"# Verification report — {book_path.name}\n")
    print(f"- Corpus:         `{book_path.relative_to(REPO)}`")
    print(f"- IA identifier:  `{ia_id}`")

    corpus_md = strip_frontmatter(load_corpus_text(book_path))
    ia_text = fetch_ia_text(ia_id)

    cw = normalize_words(corpus_md)
    iw = normalize_words(ia_text)

    print(f"\n## Word counts\n")
    print(f"- Corpus: **{len(cw):,}** words")
    print(f"- IA:     **{len(iw):,}** words")

    print(f"\n## Alignment\n")
    stats = alignment_stats(cw, iw)
    print(f"- Aligned words (longest common subsequence): "
          f"**{stats['aligned_words']:,}**")
    print(f"- SequenceMatcher ratio: **{stats['ratio']:.4f}**")
    print(
        f"- Coverage: our corpus is "
        f"{stats['aligned_words'] / max(1, len(cw)) * 100:.1f}% aligned; "
        f"IA is {stats['aligned_words'] / max(1, len(iw)) * 100:.1f}% aligned"
    )

    print(f"\n## Top divergence regions (ordered by gap size)\n")
    print(
        "Each entry shows what each source has in a gap between aligned "
        "passages. Tall gaps with mostly-noise on the IA side are OCR "
        "garbage; tall gaps with intelligible text on both sides are real "
        "differences (transcription errors or edition variations) and "
        "deserve a closer human look.\n"
    )
    for i, (size, ours, ia) in enumerate(
        top_divergences(cw, iw, stats["blocks"]),
        start=1,
    ):
        print(f"### {i}. Gap size: {size} words\n")
        print(f"**Our text:** {truncate(ours) or '(nothing)'}\n")
        print(f"**IA text:**  {truncate(ia) or '(nothing)'}\n")

    # ---------- Small-gap audit (the actual transcription concern) ----------
    print(f"\n## Small-gap audit — likely transcription concerns\n")
    print(
        "Below are gaps that are SHORT (≤40 words on each side) AND sit "
        "between two long anchor passages (≥30 words each) that align. "
        "These are exactly the shape a transcription typo, missed line, "
        "or misread word leaves behind. OCR-noise gaps (mostly short "
        "tokens — the IA Devanagari pages) and index-entry gaps (page "
        "numbers) are filtered out.\n"
    )

    audit = small_gap_audit(cw, iw, stats["blocks"])
    by_cat = {
        "text-diff": [g for g in audit if g["category"] == "text-diff"],
        "ours-missing": [g for g in audit if g["category"] == "ours-missing"],
        "ours-extra": [g for g in audit if g["category"] == "ours-extra"],
    }
    print(f"- **text-diff** (both sides have text, they differ): "
          f"{len(by_cat['text-diff'])}")
    print(f"- **ours-missing** (IA has it, our corpus does not): "
          f"{len(by_cat['ours-missing'])}")
    print(f"- **ours-extra** (our corpus has it, IA does not): "
          f"{len(by_cat['ours-extra'])}")

    cat_labels = {
        "text-diff": "Text differences (likely real transcription divergences)",
        "ours-missing": "Possibly dropped in our transcript",
        "ours-extra": "Present in our transcript, absent in IA",
    }
    for cat, items in by_cat.items():
        if not items:
            continue
        print(f"\n### {cat_labels[cat]} — {len(items)} items\n")
        items.sort(key=lambda g: -g["size"])
        # Cap at 25 per category to keep the report scannable.
        for i, g in enumerate(items[:25], start=1):
            print(f"{i}. **…{truncate(g['anchor_before'], 60)} ⟶  ⟵ {truncate(g['anchor_after'], 60)}…**")
            print(f"   - Ours: {truncate(g['ours'], 200) or '(nothing)'}")
            print(f"   - IA:   {truncate(g['ia'], 200) or '(nothing)'}")
            print()
        if len(items) > 25:
            print(f"_…{len(items) - 25} more in this category._\n")

    print(
        "---\nReports of this kind are heuristic. They surface candidates "
        "for human review; they do not automatically declare anything "
        "wrong. Edition differences (first edition vs ours), front-matter, "
        "introductions, appendices, and OCR errors all produce divergence "
        "gaps."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
