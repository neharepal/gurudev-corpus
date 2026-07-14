# RETURN WORKFLOW — after the M4 hands back `out/` (main machine)

The M4 produced `out/<work_id>.md` (latest-Surya re-OCR). This is the sequence to
grade it, replace the garbled tesseract text where Surya wins, and refresh the index —
with the embedder stale-vector gotcha handled.

Put the returned folder at `_surya_ocr_job/out/` (AirDrop drops it there).

## 1. Grade Surya vs the current text
```bash
python tools/surya_ocr/compare.py --surya-dir _surya_ocr_job/out
```
Scores each book on the audit's own metrics (Devanagari %, mojibake, decode-garbage,
header/footer leak) + a length-delta truncation guard. Prints a table, a 40%-in text
sample of each (tesseract vs Surya side by side), and writes
`tools/surya_ocr/replace_decisions.yaml`. Verdicts:
- **REPLACE** — Surya clearly cleaner, length sane → auto-marked `replace: true`.
- **REVIEW** — mixed signal; read the sample and flip to `replace: true` if you approve.
- **KEEP** — Surya no better or truncated → the SOURCE scan is the problem; keep on the
  re-source list (Internet Archive for the English titles), don't replace.

Read `out/NOTES.md` if the M4 flagged any poor-source books.

## 2. Approve
Open `tools/surya_ocr/replace_decisions.yaml`, set `replace: true` on any REVIEW you
accept (and `false` on any REPLACE you reject).

## 3. Replace text.md in place (keeps work_id; backs up the tesseract original)
```bash
python tools/surya_ocr/apply_replacements.py            # dry-run: shows the plan
python tools/surya_ocr/apply_replacements.py --apply    # do it
```
Old text is saved to `04_processed/_bak-reocr-<date>/…`; `meta.yaml` records the re-OCR.

## 4. Refresh the index — pick ONE

### Option A — defer to the Phase-2 re-embed (RECOMMENDED if Phase 2 is near)
Do nothing more now. The Phase-2 cutover does a FULL re-embed on the M4 (rebuilds every
vector from scratch), so the replaced text.md flows in automatically and the stale-vector
gotcha cannot apply. Just re-run the chunker so chunks.jsonl matches the new text:
```bash
python tools/chunker.py
```
The live app keeps serving the old index until Phase 2 lands.

### Option B — immediate targeted re-embed (updates the live app now)
Handles the gotcha by evicting the replaced works' stale vectors first:
```bash
python tools/chunker.py                                             # rebuild chunks.jsonl
python tools/surya_ocr/force_reembed.py --apply <work_id> [<id>…]   # evict old vectors (backs up)
python tools/embedder.py                                            # re-encodes evicted works only
```
`apply_replacements.py --apply` prints this exact command with the replaced ids filled in.
(The clean long-term fix is a text-hash check in the embedder — folds into the Phase-2
embedder work; until then this eviction is the safe manual path.)

## 5. Verify + record
```bash
python tools/embedder.py --help >/dev/null   # sanity
# smoke-test a query that hits a replaced book, then:
```
Append a `CORPUS_CHANGELOG.md` entry (books replaced, engine=surya, date, metric deltas)
and commit `meta.yaml` + `text.md` changes. `_bak-reocr-*` and `_surya_ocr_job/` stay
gitignored.
