# Reading Mode Book-Like Layout — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Reading Mode feel like a printed book — book-style paragraphs, a sticky Title·Chapter running head, chapters starting on fresh pages, a centered folio — without changing palette, textures, or fonts.

**Architecture:** A new pure `tools/pagination.py` groups paragraphs into pages (≤4 per page, and a chapter change forces a new page); `read_work` and the two deep-link page-mappers all call it so page numbers agree. The reader component (`chat-app/app/read/[slug]/page.tsx`) + `globals.css` apply book typography, a sticky running head, and a folio.

**Tech Stack:** Python 3.8 (FastAPI backend, pytest 5.4.3), Next.js/React + TypeScript + Tailwind (chat-app).

## Global Constraints
- Run backend Python with `/Users/neharepal/opt/anaconda3/bin/python` (has FastAPI, pytest).
- Do NOT change palette, textures, or fonts. Reading measure stays `max-w-reading: 70ch`.
- No drop cap, no justified text (Marathi has no hyphenation).
- Trunk-based: commit directly to `main`, push after each task (`git fetch` + fast-forward check first).
- Backend changes require a server restart to go live (`/admin/reload` only re-reads the index).
- Spec: `docs/superpowers/specs/2026-07-03-reading-mode-book-layout-design.md`.

---

### Task 1: Pure pagination helper

**Files:**
- Create: `tools/pagination.py`
- Test: `tools/tests/test_pagination.py`

**Interfaces:**
- Produces:
  - `PAGE_SIZE: int = 4`
  - `paginate(paragraphs: List[Dict]) -> List[List[Dict]]` — groups in doc order; new page when the running page has PAGE_SIZE paragraphs OR `chapter` changes.
  - `page_for_paragraph_index(paragraphs: List[Dict], idx: int) -> int` — 1-based page containing paragraph `idx` (clamped to ≥0 and to last page).
  - `is_chapter_start(pages: List[List[Dict]], page_num: int) -> bool` — True if 1-based `page_num` begins a new chapter (page 1 always True).

- [ ] **Step 1: Write the failing test** — `tools/tests/test_pagination.py`

```python
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from pagination import paginate, page_for_paragraph_index, is_chapter_start, PAGE_SIZE

def _p(n, chapter):
    return {"n": n, "chapter": chapter, "body": f"para {n}"}

def test_chapter_change_forces_new_page():
    pages = paginate([_p(1, "A"), _p(2, "A"), _p(3, "B")])
    assert [len(pg) for pg in pages] == [2, 1]
    assert [pg[0]["chapter"] for pg in pages] == ["A", "B"]

def test_long_chapter_splits_by_page_size():
    pages = paginate([_p(i, "A") for i in range(1, PAGE_SIZE * 2 + 2)])  # 9 paras
    assert [len(pg) for pg in pages] == [PAGE_SIZE, PAGE_SIZE, 1]

def test_every_paragraph_in_exactly_one_page_in_order():
    paras = [_p(1, "A"), _p(2, "B"), _p(3, "B"), _p(4, "B"), _p(5, "B"), _p(6, "B")]
    flat = [pa for pg in paginate(paras) for pa in pg]
    assert flat == paras

def test_page_for_paragraph_index():
    paras = [_p(1, "A"), _p(2, "A"), _p(3, "B"), _p(4, "B")]  # pages [A,A],[B,B]
    assert page_for_paragraph_index(paras, 0) == 1
    assert page_for_paragraph_index(paras, 1) == 1
    assert page_for_paragraph_index(paras, 2) == 2
    assert page_for_paragraph_index(paras, 99) == 2   # clamp past end

def test_is_chapter_start():
    paras = [_p(1, "A"), _p(2, "A"), _p(3, "B"), _p(4, "B")]
    pages = paginate(paras)
    assert is_chapter_start(pages, 1) is True
    assert is_chapter_start(pages, 2) is True

def test_continuation_page_is_not_chapter_start():
    pages = paginate([_p(i, "A") for i in range(1, PAGE_SIZE + 3)])  # [4],[2] same chapter
    assert is_chapter_start(pages, 1) is True
    assert is_chapter_start(pages, 2) is False

def test_empty():
    assert paginate([]) == []
    assert page_for_paragraph_index([], 0) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/neharepal/opt/anaconda3/bin/python -m pytest tools/tests/test_pagination.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'pagination'`.

- [ ] **Step 3: Write minimal implementation** — `tools/pagination.py`

```python
"""Reading-page pagination for the corpus reader.

A page holds up to PAGE_SIZE paragraphs, BUT a change of `chapter` always starts
a new page (each book chapter opens on a fresh reader page). Pure and
dependency-free so read_work + the two deep-link page mappers agree on page
numbers. Spec: docs/superpowers/specs/2026-07-03-reading-mode-book-layout-design.md
"""
from __future__ import annotations
from typing import Any, Dict, List

PAGE_SIZE = 4


def paginate(paragraphs: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    pages: List[List[Dict[str, Any]]] = []
    current: List[Dict[str, Any]] = []
    current_chapter: Any = None
    for para in paragraphs:
        chapter = para.get("chapter", "")
        if current and (chapter != current_chapter or len(current) >= PAGE_SIZE):
            pages.append(current)
            current = []
        if not current:
            current_chapter = chapter
        current.append(para)
    if current:
        pages.append(current)
    return pages


def page_for_paragraph_index(paragraphs: List[Dict[str, Any]], idx: int) -> int:
    if idx < 0:
        idx = 0
    pages = paginate(paragraphs)
    seen = 0
    for page_num, page in enumerate(pages, start=1):
        seen += len(page)
        if idx < seen:
            return page_num
    return max(1, len(pages))


def is_chapter_start(pages: List[List[Dict[str, Any]]], page_num: int) -> bool:
    if page_num <= 1:
        return True
    if page_num > len(pages):
        return False
    return pages[page_num - 1][0].get("chapter", "") != pages[page_num - 2][-1].get("chapter", "")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/neharepal/opt/anaconda3/bin/python -m pytest tools/tests/test_pagination.py -q`
Expected: PASS (8 passed).

- [ ] **Step 5: Commit**

```bash
git add tools/pagination.py tools/tests/test_pagination.py
git commit -m "read: pure chapter-aware pagination helper + tests"
```

---

### Task 2: Wire pagination into the backend

**Files:**
- Modify: `tools/server.py` (imports; `reading_page_for_offset` ~L312; `reading_page_for_body` ~L366; `read_work` ~L1197-1219; remove now-unused `_PAGE_SIZE` ~L188)

**Interfaces:**
- Consumes: `paginate`, `page_for_paragraph_index`, `is_chapter_start` from Task 1.
- Produces: `read_work` JSON gains `"chapterStart": bool`; pagination is chapter-aware everywhere.

- [ ] **Step 1: Add the import** (near `import query_translation`)

```python
from pagination import paginate, page_for_paragraph_index, is_chapter_start
```

- [ ] **Step 2: `reading_page_for_offset` — replace the final return**

Replace:
```python
    return (target_idx // _PAGE_SIZE) + 1
```
with:
```python
    return page_for_paragraph_index(all_paragraphs, target_idx)
```

- [ ] **Step 3: `reading_page_for_body` — replace the matched return**

Replace:
```python
            if key in _norm_for_match(para["body"]):
                return (i // _PAGE_SIZE) + 1
```
with:
```python
            if key in _norm_for_match(para["body"]):
                return page_for_paragraph_index(paragraphs, i)
```

- [ ] **Step 4: `read_work` — replace the slice block with chapter-aware pages**

Replace:
```python
    PAGE_SIZE = _PAGE_SIZE
    total_pages = math.ceil(total / PAGE_SIZE)
    page = max(1, min(page, total_pages))
    start = (page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    page_paras = all_paragraphs[start:end]

    chapter = page_paras[0]["chapter"] if page_paras else ""
```
with:
```python
    pages = paginate(all_paragraphs)
    total_pages = len(pages)
    page = max(1, min(page, total_pages))
    page_paras = pages[page - 1]
    chapter = page_paras[0]["chapter"] if page_paras else ""
    chapter_start = is_chapter_start(pages, page)
```
(`total = len(all_paragraphs)` and its zero-guard above stay unchanged.)

- [ ] **Step 5: `read_work` — add `chapterStart` to the response dict**

Replace:
```python
        "chapter": chapter,
        "totalPages": total_pages,
```
with:
```python
        "chapter": chapter,
        "chapterStart": chapter_start,
        "totalPages": total_pages,
```

- [ ] **Step 6: Remove the now-unused `_PAGE_SIZE`**

Delete the line `_PAGE_SIZE = 4` (~L188). Confirm no references remain:
Run: `grep -n "_PAGE_SIZE" tools/server.py`
Expected: no output.

- [ ] **Step 7: Syntax check**

Run: `/Users/neharepal/opt/anaconda3/bin/python -m py_compile tools/server.py`
Expected: no output (exit 0).

- [ ] **Step 8: Restart the server and verify chapter-aware pagination + deep-link**

```bash
# stop current server, then start fresh (needs ANTHROPIC_API_KEY in env):
kill "$(lsof -nP -iTCP:8765 -sTCP:LISTEN -t | head -1)" 2>/dev/null
GURUDEV_BACKEND_PORT=8765 /Users/neharepal/opt/anaconda3/bin/python tools/server.py >/tmp/gd-server.log 2>&1 &
until grep -q "\[startup\] ready" /tmp/gd-server.log; do sleep 2; done
# charitra-tatvajnan-tulpule has 4 chapters -> page 1 must be a chapter start:
curl -s "http://localhost:8765/read/charitra-tatvajnan-tulpule?lang=mr&page=1" \
  | /Users/neharepal/opt/anaconda3/bin/python -c "import sys,json; d=json.load(sys.stdin); print('chapterStart:', d['chapterStart'], '| chapter:', d['chapter'], '| totalPages:', d['totalPages'])"
```
Expected: `chapterStart: True`, a non-empty `chapter`, `totalPages` ≥ 4. No page mixes two chapters (spot-check a couple of pages: each page's paragraphs share one chapter).

- [ ] **Step 9: Commit**

```bash
git add tools/server.py
git commit -m "read: chapter-aware pagination via shared helper; add chapterStart"
```

---

### Task 3: Sticky running head + book paragraphs (frontend)

**Files:**
- Modify: `chat-app/data/mock-conversations.ts` (add `chapterStart` to the `ReadingPage` type)
- Modify: `chat-app/app/globals.css` (running head, book paragraph, chapter-open classes)
- Modify: `chat-app/app/read/[slug]/page.tsx` (sticky head; book paragraph rendering)

**Interfaces:**
- Consumes: `read_work` response `{ workTitle, author, chapter, chapterStart, totalPages, paragraphs }` (Task 2).
- Note: no frontend test runner in this repo — verify with `npx tsc --noEmit` + a manual visual check.

- [ ] **Step 1: Add `chapterStart` to the `ReadingPage` type**

In `chat-app/data/mock-conversations.ts`, in the `ReadingPage` type (the one with `workTitle`, `author`, `chapter`, `totalPages`, `paragraphs`), add after `chapter`:
```ts
  chapterStart?: boolean;
```

- [ ] **Step 2: Add CSS** — append to `chat-app/app/globals.css`

```css
/* Reading Mode — book layout (2026-07-03) */
.gd-runhead {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.5rem 0 0.4rem;
  font-size: 14px;
  color: var(--text-secondary);
  border-bottom: 1px solid var(--border-soft);
  /* Replicate the body's fixed paper so the sticky bar's texture aligns
     seamlessly and masks text scrolling beneath it. */
  background-color: var(--bg-page);
  background-image: url("/paper-bg.jpg");
  background-size: 100vw 100vh;
  background-position: center top;
  background-repeat: no-repeat;
  background-attachment: fixed;
}
.gd-read-p {
  text-indent: 1.4em;
  margin: 0;
}
.gd-read-p--flush {
  text-indent: 0;
}
.gd-chapter-open {
  text-align: center;
  margin: 1.6em 0 1em;
  font-weight: 600;
}
.gd-folio {
  text-align: center;
  margin-top: 2rem;
  font-size: 13px;
  color: var(--text-secondary);
}
```

- [ ] **Step 3: Add the sticky running head** — in `page.tsx`, as the FIRST child inside `<main className="mx-auto flex ...">` (before the existing `<header>`)

```tsx
      <div className={`gd-runhead ${isMr ? "font-deva" : ""}`}>
        <span>{pageData?.workTitle ?? slug.replace(/-/g, " ")}</span>
        <span>{pageData?.chapter ?? ""}</span>
      </div>
```

- [ ] **Step 4: De-duplicate chapter in the masthead** — in the existing header's author line, drop `· chapter`

Replace:
```tsx
            {pageData ? `${pageData.author} · ${pageData.chapter}` : ""}
```
with:
```tsx
            {pageData ? pageData.author : ""}
```

- [ ] **Step 5: Apply book paragraph styling** — replace the "Normal paragraph display" `<p>` (~L604)

Replace:
```tsx
                  <p
                    className="text-[17.5px]"
                    style={{
                      color: "var(--text-primary)",
                      lineHeight: 1.7,
                    }}
                  >
                    {para.body}
                  </p>
```
with (the first paragraph on a chapter-start page renders flush; `idx` is the map index of the paragraph):
```tsx
                  <p
                    className={`gd-read-p text-[17.5px] ${
                      idx === 0 && pageData?.chapterStart ? "gd-read-p--flush" : ""
                    }`}
                    style={{
                      color: "var(--text-primary)",
                      lineHeight: 1.7,
                    }}
                  >
                    {para.body}
                  </p>
```
Ensure the enclosing `.map(...)` exposes the index — if it is `paragraphs.map((para) => ...)`, change to `paragraphs.map((para, idx) => ...)`.

- [ ] **Step 6: Remove the inter-paragraph gap** — the paragraph wrapper currently uses `className="mb-7"` (~L523). Change `mb-7` to `mb-0` so paragraphs run together (book style).

- [ ] **Step 7: Typecheck**

Run: `cd chat-app && npx tsc --noEmit`
Expected: exit 0, no errors.

- [ ] **Step 8: Visual check** (dev server fast-refreshes; open a Marathi work opened from a citation)
Expected: slim `Title … Chapter` bar pinned at top while scrolling; paragraphs indented and gap-free; chapter-opening paragraph flush.

- [ ] **Step 9: Commit**

```bash
git add chat-app/data/mock-conversations.ts chat-app/app/globals.css "chat-app/app/read/[slug]/page.tsx"
git commit -m "read: sticky Title·Chapter running head + book-style paragraphs"
```

---

### Task 4: Folio + hover-revealed correction (frontend polish)

**Files:**
- Modify: `chat-app/app/read/[slug]/page.tsx` (centered folio below the article; correction link on hover)

**Interfaces:**
- Consumes: `.gd-folio` class (Task 3); existing `lbl.pageXofY`, `total`, `sliderValue`.

- [ ] **Step 1: Move the folio below the text** — remove the right-aligned page readout under the slider

Replace the readout `<div>` under the slider:
```tsx
        <div
          className={`mt-1.5 text-[12px] text-right ${isMr ? "font-deva" : ""}`}
          style={{ color: "var(--text-secondary)" }}
        >
          {lbl.pageXofY(sliderValue, total)}
        </div>
```
with nothing (delete it), and add a centered folio immediately AFTER the closing `</article>`:
```tsx
      <div className={`gd-folio ${isMr ? "font-deva" : ""}`}>
        {lbl.pageXofY(sliderValue, total)}
      </div>
```

- [ ] **Step 2: Reveal the correction link on hover** — make each paragraph block a `group` and hide the correction button until hover/focus

On the paragraph wrapper (the element whose class you changed to `mb-0` in Task 3 Step 6), add `group`:
```tsx
                <div className="mb-0 group">
```
On the "suggest correction" `<button>` (~L615), add hover/focus reveal to its `className`:
```tsx
                    className={`mt-1 text-[11px] opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100 ${isMr ? "font-deva" : ""}`}
```

- [ ] **Step 3: Typecheck**

Run: `cd chat-app && npx tsc --noEmit`
Expected: exit 0.

- [ ] **Step 4: Visual check**
Expected: centered "Page X of Y" below the text; correction link hidden until you hover a paragraph (still reachable by keyboard focus).

- [ ] **Step 5: Commit**

```bash
git add "chat-app/app/read/[slug]/page.tsx"
git commit -m "read: centered folio + hover-revealed correction link"
```

---

## Self-Review Notes
- **Spec coverage:** §1 paragraphs → T3 S5-6; §2 sticky header → T3 S2-4; §3 chapter-aware pagination + chapterStart → T1 + T2; §4 folio → T4 S1; §5 hover correction → T4 S2. All covered.
- **Type consistency:** `paginate`/`page_for_paragraph_index`/`is_chapter_start` names identical across T1 (def), T2 (use). `chapterStart` identical across T2 (backend), T3 (type + `pageData?.chapterStart`).
- **Out of scope (unchanged):** palette, textures, fonts, 70ch measure, no drop cap, no justification.
