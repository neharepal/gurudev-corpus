#!/usr/bin/env python3
"""
sweep_canonical.py — for every Gurudev book that has a text.md, search IA
for a matching upload, run `verify_canonical.py` against it, and aggregate
a single summary report.

Output:
  04_processed/canonical_audit/
    ├── mapping.yaml         # book → IA id chosen (and runners-up)
    ├── <book-slug>.md       # per-book verification report
    └── SUMMARY.md           # one-line per book + aggregated text-diffs

Usage:
    python3 tools/sweep_canonical.py

Reads books from 01_canonical/gurudev_ranade/books/. Skips books with no
text.md. Skips books where no plausible IA match is found.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BOOKS_DIR = REPO / "01_canonical" / "gurudev_ranade" / "books"
OUT_DIR = REPO / "04_processed" / "canonical_audit"
VERIFY = REPO / "tools" / "verify_canonical.py"


def list_books_with_text() -> list[Path]:
    out: list[Path] = []
    for d in sorted(BOOKS_DIR.iterdir()):
        if d.is_dir() and (
            list(d.rglob("text.md"))
        ):
            out.append(d)
    return out


def humanize_slug(slug: str) -> str:
    return slug.replace("-", " ")


def search_ia(title: str) -> list[dict]:
    """Search IA for items by title + author=Ranade. Return up to 10 hits."""
    q = (
        f'title:({title}) AND '
        f'creator:(Ranade)'
    )
    params = {
        "q": q,
        "fl[]": "identifier,title,creator,year,mediatype",
        "rows": "10",
        "output": "json",
    }
    url = (
        "https://archive.org/advancedsearch.php?"
        + urllib.parse.urlencode(params, doseq=True)
    )
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"  [search error] {e}", file=sys.stderr)
        return []
    docs = data.get("response", {}).get("docs", [])
    # Prefer items with mediatype=texts.
    docs.sort(
        key=lambda d: (
            0 if d.get("mediatype") == "texts" else 1,
            int(str(d.get("year") or "9999")[:4]) if str(d.get("year") or "").strip() else 9999,
        )
    )
    return docs


def pick_best_match(slug: str, docs: list[dict]) -> dict | None:
    """Pick the candidate whose normalized title best matches the slug."""
    if not docs:
        return None
    slug_tokens = set(slug.lower().replace("-", " ").split())
    # Filter out obvious noise (very short titles, audio, etc.)
    candidates = []
    for d in docs:
        title = (d.get("title") or "").lower()
        if not title:
            continue
        title_tokens = set(re.findall(r"[a-z]+", title))
        overlap = slug_tokens & title_tokens
        if not overlap:
            continue
        score = len(overlap) / max(1, len(slug_tokens | title_tokens))
        candidates.append((score, d))
    if not candidates:
        return None
    candidates.sort(key=lambda c: -c[0])
    # Require at least 50% token overlap or 3+ tokens shared.
    top_score, top = candidates[0]
    overlap = slug_tokens & set(re.findall(r"[a-z]+", (top.get("title") or "").lower()))
    if top_score < 0.5 and len(overlap) < 3:
        return None
    return top


def verify_book(book_dir: Path, ia_id: str) -> tuple[Path, dict]:
    """Run verify_canonical.py on the book. Returns (report path, stats)."""
    rel = book_dir.relative_to(REPO)
    out_path = OUT_DIR / f"{book_dir.name}.md"
    proc = subprocess.run(
        ["python3", str(VERIFY), str(rel), ia_id],
        capture_output=True,
        text=True,
        timeout=600,
    )
    out_path.write_text(proc.stdout, encoding="utf-8")
    # Pull headline numbers from the report text.
    stats = {}
    for k, pat in [
        ("corpus_words", r"Corpus:\s*\*\*([\d,]+)\*\*"),
        ("ia_words", r"IA:\s*\*\*([\d,]+)\*\*"),
        ("ratio", r"ratio:\s*\*\*([\d.]+)\*\*"),
        ("text_diff", r"\*\*text-diff\*\*[^:]+:\s*(\d+)"),
        ("ours_missing", r"\*\*ours-missing\*\*[^:]+:\s*(\d+)"),
        ("ours_extra", r"\*\*ours-extra\*\*[^:]+:\s*(\d+)"),
    ]:
        m = re.search(pat, proc.stdout)
        if m:
            v = m.group(1).replace(",", "")
            stats[k] = float(v) if "." in v else int(v)
    return out_path, stats


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    books = list_books_with_text()
    print(f"# Canonical audit — {len(books)} books\n", file=sys.stderr)

    mapping: dict[str, dict] = {}
    rows: list[dict] = []

    for i, book in enumerate(books, start=1):
        slug = book.name
        title = humanize_slug(slug)
        print(f"\n[{i}/{len(books)}] {slug}", file=sys.stderr)

        hits = search_ia(title)
        match = pick_best_match(slug, hits)
        if not match:
            print(f"  (no IA match)", file=sys.stderr)
            mapping[slug] = {
                "ia_id": None,
                "candidates": [
                    {"id": h.get("identifier"), "title": h.get("title"),
                     "year": h.get("year")}
                    for h in hits[:5]
                ],
            }
            rows.append({"slug": slug, "ia_id": None, "status": "no-match"})
            continue

        ia_id = match["identifier"]
        print(f"  → IA: {ia_id} ({match.get('title','?')[:60]})", file=sys.stderr)
        mapping[slug] = {
            "ia_id": ia_id,
            "ia_title": match.get("title"),
            "ia_year": match.get("year"),
            "candidates": [
                {"id": h.get("identifier"), "title": h.get("title"),
                 "year": h.get("year")}
                for h in hits[:5]
            ],
        }

        try:
            t0 = time.time()
            _, stats = verify_book(book, ia_id)
            elapsed = time.time() - t0
            print(
                f"  ratio={stats.get('ratio','?')} "
                f"text-diff={stats.get('text_diff','?')} "
                f"missing={stats.get('ours_missing','?')} "
                f"extra={stats.get('ours_extra','?')} "
                f"({elapsed:.0f}s)",
                file=sys.stderr,
            )
            rows.append({"slug": slug, "ia_id": ia_id, "status": "ok",
                         **stats})
        except subprocess.TimeoutExpired:
            print(f"  (timeout)", file=sys.stderr)
            rows.append({"slug": slug, "ia_id": ia_id, "status": "timeout"})
        except Exception as e:
            print(f"  (verify error: {e})", file=sys.stderr)
            rows.append({"slug": slug, "ia_id": ia_id, "status": "error",
                         "error": str(e)})

    # Write YAML-ish mapping.
    map_path = OUT_DIR / "mapping.yaml"
    with map_path.open("w", encoding="utf-8") as f:
        for slug, info in mapping.items():
            f.write(f"{slug}:\n")
            if info.get("ia_id"):
                f.write(f"  ia_id: {info['ia_id']}\n")
                if info.get("ia_title"):
                    f.write(f"  ia_title: \"{info['ia_title']}\"\n")
                if info.get("ia_year"):
                    f.write(f"  ia_year: {info['ia_year']}\n")
            else:
                f.write(f"  ia_id: null\n")
            if info.get("candidates"):
                f.write(f"  candidates:\n")
                for c in info["candidates"]:
                    f.write(
                        f"    - id: {c.get('id')}\n"
                        f"      title: \"{c.get('title')}\"\n"
                        f"      year: {c.get('year')}\n"
                    )

    # Write SUMMARY.md.
    summary = OUT_DIR / "SUMMARY.md"
    with summary.open("w", encoding="utf-8") as f:
        f.write("# Canonical audit — summary\n\n")
        f.write("| Book | IA | Ratio | text-diff | ours-missing | ours-extra |\n")
        f.write("|---|---|---:|---:|---:|---:|\n")
        for r in rows:
            slug = r["slug"]
            ia = r.get("ia_id") or "—"
            ratio = r.get("ratio")
            ratio_s = f"{ratio:.3f}" if isinstance(ratio, float) else "—"
            td = r.get("text_diff", "—")
            om = r.get("ours_missing", "—")
            oe = r.get("ours_extra", "—")
            f.write(f"| {slug} | `{ia}` | {ratio_s} | {td} | {om} | {oe} |\n")
        f.write(
            "\n*See per-book reports in this directory and `mapping.yaml` "
            "for the IA candidates considered.*\n"
        )

    print(f"\nWrote {summary} and {map_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
