#!/usr/bin/env python3
"""Assemble Surya OCR-2 per-work JSON into per-work markdown.

Surya OCR-2 (llamacpp backend) writes a single results.json per work with the
shape:

    { "<work_id>": [ {page, blocks:[{reading_order,label,html,...}], ...}, ... ] }

Blocks carry semantic labels (Text, SectionHeader, PageHeader, ...) and their
recognized content is HTML (mostly `<p>...</p>` with `<br/>` line breaks). We
strip the tags to plain text, drop page headers (page numbers), and emit one
paragraph per block separated by blank lines so downstream chunkers can pick
them up as arthasahit "entry" units.

Separated from OCR so that formatting fixes don't require re-running the slow
recognition step.
"""
from __future__ import annotations

import json
import os
import glob
import re
import sys

RAW = "out_raw"
OUT = "out"
os.makedirs(OUT, exist_ok=True)

# Blocks whose text we drop entirely (not part of the reading flow).
_DROP_LABELS = {"PageHeader", "PageFooter", "Footnote"}

# Minimal HTML tag stripper: turn <br/> into newline, drop other tags, decode
# a few common entities. Surya's html field is not full HTML — just <p>, <br/>,
# <h1..h6>, sometimes style attrs — so a full parser would be overkill.
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


def html_to_text(html: str) -> str:
    if not html:
        return ""
    s = _BR_RE.sub("\n", html)
    s = _TAG_RE.sub("", s)
    s = (
        s.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
    )
    # Collapse only trailing whitespace on each line; keep line breaks so verse
    # padas that used <br/> stay separated.
    return "\n".join(line.rstrip() for line in s.splitlines()).strip()


def iter_pages(obj):
    """Yield page dicts from the results.json shape, tolerating drift.

    Preferred shape: top-level dict with one key (the work id) -> list of pages.
    Fallback: any dict with `blocks` is a page; walk recursively.
    """
    if isinstance(obj, dict):
        if len(obj) == 1:
            (only_v,) = obj.values()
            if isinstance(only_v, list) and only_v and isinstance(only_v[0], dict) \
                    and "blocks" in only_v[0]:
                yield from only_v
                return
        if "blocks" in obj:
            yield obj
            return
        for v in obj.values():
            yield from iter_pages(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from iter_pages(v)


def page_no(page: dict, i: int) -> int:
    for k in ("page", "page_number", "page_idx"):
        v = page.get(k)
        if isinstance(v, int):
            return v
    return i


def assemble_page(page: dict) -> list[str]:
    """Return paragraphs (plain text) for one page, in reading order."""
    blocks = page.get("blocks", []) or []

    def order_key(b):
        v = b.get("reading_order")
        return v if isinstance(v, int) else 10**9

    paras: list[str] = []
    for b in sorted(blocks, key=order_key):
        if not isinstance(b, dict):
            continue
        if b.get("skipped") or b.get("error"):
            continue
        label = b.get("label")
        if label in _DROP_LABELS:
            continue
        text = html_to_text(b.get("html") or "")
        if not text:
            continue
        paras.append(text)
    return paras


def work_id_for(path: str) -> str:
    parts = path.replace("\\", "/").split("/")
    try:
        i = parts.index(RAW)
    except ValueError:
        return os.path.splitext(os.path.basename(path))[0]
    if i + 1 < len(parts):
        return parts[i + 1]
    return os.path.splitext(os.path.basename(path))[0]


def main():
    results = sorted(set(
        glob.glob(os.path.join(RAW, "**", "results.json"), recursive=True)
    ))
    if not results:
        print(f"No results.json under {RAW}/ — run the OCR step first.")
        sys.exit(1)

    seen: set[str] = set()
    for jp in results:
        wid = work_id_for(jp)
        if wid in seen:
            continue
        seen.add(wid)
        try:
            with open(jp, encoding="utf-8") as f:
                obj = json.load(f)
        except Exception as e:
            print(f"  SKIP {jp}: {e}")
            continue

        pages_ordered = sorted(iter_pages(obj), key=lambda p: page_no(p, 0))
        page_paras: list[list[str]] = [assemble_page(p) for p in pages_ordered]

        parts: list[str] = []
        for paras in page_paras:
            for para in paras:
                parts.append(para)
        text = "\n\n".join(parts).strip() + "\n"

        outp = os.path.join(OUT, f"{wid}.md")
        with open(outp, "w", encoding="utf-8") as f:
            f.write(text)
        npages = len(pages_ordered)
        nblocks = sum(len(p) for p in page_paras)
        print(f"  {wid:40s} pages={npages:4d}  blocks={nblocks:5d}  "
              f"chars={len(text):>9,}  -> {outp}")

    print(f"\nDone. {len(seen)} works assembled into {OUT}/")


if __name__ == "__main__":
    main()
