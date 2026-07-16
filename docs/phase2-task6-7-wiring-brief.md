# Phase-2 Task 6/7 wiring — execution brief (do on the M4, AFTER the re-embed)

Concrete insertion points for the `ENABLE_SMALL_TO_BIG` child→parent wiring (RFC-017,
Option B). The pieces already merged: `expand_children_to_parents()` (server.py ~606),
`_load_parents_by_id()` + `STATE.parents_by_id` (server.py ~656/703). What's left is
consuming them in the request path. **Build this test-driven against the real child
index — it was deliberately not wired blind.**

## Key fact that shapes this
On the NEW child index every chunk is a small child (sentence/verse). So with the flag
OFF the answer model would get only tiny snippets and lose context — the classic
small-chunk failure. **On the child index the flag should be ON**; OFF is only the
fallback that keeps the OLD flat index working. Gate on:
`ENABLE_SMALL_TO_BIG=1` AND `STATE.parents_by_id` non-empty (both true only post-re-embed).

## Insertion points

1. **`_retrieve` (server.py ~592–603), after `out` is built.**
   When gated on: for each returned child dict, attach `parent_id = meta.get("parent_id")`
   and `parent_text = STATE.parents_by_id[parent_id]["text"]`, and set the citation anchor
   `text = meta.get("cite_text") or meta.get("text")` (child stays the anchor — Option B).
   Dedup parents so the same parent section isn't repeated across sibling children
   (reuse `expand_children_to_parents` grouping, or dedup inline).

2. **`build_user_message` / `build_pravachan_user_message` / `build_reading_user_message`
   (server.py ~1459–1465).**
   Feed the model the **parent section** as the context to read, with the child
   `cite_text` flagged as the exact span to quote. Keep one context block per distinct
   parent; list its matched children as the quotable anchors. Do NOT paste every child's
   parent redundantly.

3. **Splice / grounding — leave the contract unchanged (Option B).**
   `grounding.enforce_qa` / `verify_citations` still check that the cited span exists in
   the supplied passages; the supplied quotable span is now `cite_text`. Arthasahit
   children have `cite_text` = verse only (meaning absent), so the meaning can never be
   cited — that's the #35 guarantee, now automatic.

4. **Read-in-full (`_enrich_citation_readpage`, server.py ~1471).**
   It anchors readPage on the verbatim quote inside the work's `text.md` via
   `meta.source_path` — unchanged and drift-proof, since the quote is the child
   `cite_text` which is a verbatim substring of `text.md`. Confirm on one canonical and
   one arthasahit citation.

## Validate (the acceptance gates)
- `python tools/eval_retrieval.py --verbose` — the PHASE2 "lightning" buried-sentence case
  (added to GOLD) now hits `devotee` / `nimbargi-maharaj-charitra-athavani-mr` in top_k;
  existing doctrinal/entity cases do NOT regress.
- Unit: an arthasahit citation's spliced quote == the verse, never the sadhak meaning.
- Live smoke with `ENABLE_SMALL_TO_BIG=1`: a query hitting a re-OCR'd book returns clean
  Surya text; grounding/enforce still yields cross-language citations; Read-in-full jumps
  to the right page.
- Then make the flag the default (or set it in the M4 run config) once green.

## Notes
- `max_per_source` (the per-work breadth cap, server.py ~1436) becomes effectively a
  per-parent cap once expansion runs; tune `top_k`/`candidates` (currently qa top_k=12,
  candidates=100) — the child pool is ~17× denser, so candidates likely needs raising.
- Ledger: `.superpowers/sdd/progress.md` (Task 6 DONE_WITH_CONCERNS; this is the deferred
  6/7 combined wiring). Update it when green.
