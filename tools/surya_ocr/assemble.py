#!/usr/bin/env python3
"""Assemble Surya's per-page JSON output into one markdown file per work.

Separated from the OCR step on purpose: OCR is slow (writes out_raw/*.json,
cached), assembly is instant. If the formatting needs tweaking we re-run ONLY
this, never the OCR.

Reads:  out_raw/**/results.json  (whatever surya_ocr wrote)
Writes: out/<work_id>.md
Defensive to surya's JSON schema drift: it walks the structure, finds the list
of page objects (each carrying `text_lines`), orders by page, and joins the
recognized line text.
"""
import json, os, glob, sys

RAW = "out_raw"
OUT = "out"
os.makedirs(OUT, exist_ok=True)


def pages_from_obj(obj):
    """Yield (page_index, [line_text,...]) from any surya results.json shape."""
    def is_page(d):
        return isinstance(d, dict) and "text_lines" in d

    def walk(node):
        if is_page(node):
            yield node
        elif isinstance(node, dict):
            for v in node.values():
                yield from walk(v)
        elif isinstance(node, list):
            for v in node:
                yield from walk(v)

    pages = list(walk(obj))
    # order by explicit page number if present, else discovery order
    def pageno(p, i):
        for k in ("page", "page_number", "page_idx"):
            if isinstance(p.get(k), int):
                return p[k]
        return i
    for i, p in enumerate(sorted(pages, key=lambda p: pageno(p, 0))):
        lines = []
        for ln in p.get("text_lines", []):
            t = (ln.get("text") or "").strip() if isinstance(ln, dict) else ""
            if t:
                lines.append(t)
        yield pageno(p, i), lines


def work_id_for(path):
    # out_raw/<work_id>/results.json  ->  <work_id>
    parts = path.replace("\\", "/").split("/")
    for seg in reversed(parts[:-1]):
        if seg and seg != RAW:
            return seg
    return os.path.splitext(os.path.basename(path))[0]


def main():
    results = glob.glob(os.path.join(RAW, "**", "results.json"), recursive=True)
    results += glob.glob(os.path.join(RAW, "**", "*.json"), recursive=True)
    results = sorted(set(results))
    if not results:
        print(f"No JSON under {RAW}/ — run the OCR step first.")
        sys.exit(1)
    seen = set()
    for jp in results:
        wid = work_id_for(jp)
        if wid in seen:
            continue
        seen.add(wid)
        try:
            obj = json.load(open(jp, encoding="utf-8"))
        except Exception as e:
            print(f"  SKIP {jp}: {e}")
            continue
        chunks = []
        npages = 0
        for pno, lines in pages_from_obj(obj):
            npages += 1
            if lines:
                chunks.append("\n".join(lines))
        text = "\n\n".join(chunks).strip() + "\n"
        outp = os.path.join(OUT, f"{wid}.md")
        with open(outp, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"  {wid:38} {npages:4d} pages  {len(text):>8,} chars -> {outp}")
    print(f"\nDone. {len(seen)} works assembled into {OUT}/")


if __name__ == "__main__":
    main()
