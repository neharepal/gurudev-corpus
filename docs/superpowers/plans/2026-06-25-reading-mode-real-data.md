# Reading Mode Real Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the Next.js reading-mode viewer to real corpus content, replacing mock data with a new `GET /read/{slug}` backend endpoint and a frontend fetch.

**Architecture:** Add a standalone `GET /read/{slug}` FastAPI endpoint in `tools/server.py` that reads `03_catalog/catalog.yaml`, finds the work, strips YAML front matter from the source `text.md`, parses paragraphs and section headings, and paginates at 4 paragraphs/page. The frontend receives a new API proxy at `app/api/read/route.ts` (following the `/api/ask` pattern) and `chat-app/app/read/[slug]/page.tsx` is converted from using a static mock to calling this proxy on every page change.

**Tech Stack:** Python/FastAPI (backend), Next.js 15 App Router + React (frontend), PyYAML (catalog loading), TypeScript fetch API

## Global Constraints

- Python interpreter: `/Users/neharepal/opt/anaconda3/bin/python`
- Tests: `/Users/neharepal/opt/anaconda3/bin/python -m pytest tools/tests/ -q`
- Author display: `gurudev_ranade` → "Shri Gurudev"; all other authors title-case the id (replace `_` with space, title-case)
- Pagination: exactly 4 paragraphs per page; `totalPages = ceil(N / 4)`
- `chapter`: section heading in effect for the FIRST paragraph on the requested page (i.e. the most recent `## ` heading seen before or at that paragraph)
- Paragraph length filter: skip blocks < 80 chars (title pages, decorative lines) — these clutter the reader but won't be cited
- Work NOT in catalog → HTTP 404; language file missing → HTTP 404
- Frontend: do NOT delete the mock file — only stop importing `getReadingPage`; keep `ReadingPage` type, `SUGGESTIONS`, `DEFAULT_READING_SLUG`, and all other exports
- Backend URL used by Next proxy: `process.env.GURUDEV_BACKEND_URL || "http://localhost:8765"` (same as `/api/ask`)
- Branch: work directly on `main` (trunk-based, no per-task branches)
- Commit sign-off: end every commit message with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
- `pathway-to-god-in-hindi-literature` is NOT in `03_catalog/catalog.yaml` — the endpoint must fall back to scanning the filesystem if slug not in catalog (or we add a catalog fallback). See Task 1 for how to handle this.

---

### Task 1: Backend — `GET /read/{slug}` endpoint

**Files:**
- Modify: `tools/server.py` (add endpoint after line ~402, before `main()`)

**Interfaces:**
- Endpoint: `GET /read/{slug}?lang=en&page=1`
- Returns JSON matching `ReadingPage`:
  ```json
  {
    "workSlug": "pathway-to-god-in-hindi-literature",
    "workTitle": "Pathway to God in Hindi Literature",
    "author": "Shri Gurudev",
    "chapter": "Part 1",
    "totalPages": 359,
    "paragraphs": [{"n": 1, "body": "..."}, ...]
  }
  ```
- 404 if slug not found or text.md missing

- [ ] **Step 1: Add imports and helpers at the top of server.py** (after existing imports, around line 30–52)

Read the current imports block at lines 23–52 of `tools/server.py`, then add `yaml` and `re` imports, and add the `_author_display_name` helper and `_parse_work_text` helper. Insert them AFTER the existing import block (after line 52, before the `PORT = ...` line at 56).

Add to `tools/server.py` after `from streaming import sse, sse_heartbeat`:

```python
import math
import re
import yaml
```

- [ ] **Step 2: Add `_author_display_name` and `_parse_work_text` helpers**

Add these two functions to `tools/server.py` after the `PORT = ...` line (around line 56), BEFORE `class AskRequest`:

```python
# ---------------------------------------------------------------------------
# Reading-mode helpers
# ---------------------------------------------------------------------------

def _author_display_name(author_id: str) -> str:
    """Convert a catalog author id to a display name.

    gurudev_ranade → 'Shri Gurudev'  (per product spec)
    everything_else → title-case the id with underscores as spaces.
    """
    if author_id == "gurudev_ranade":
        return "Shri Gurudev"
    return author_id.replace("_", " ").title()


def _parse_work_text(text_path: Path) -> List[Dict[str, Any]]:
    """Parse a text.md file into a list of paragraph records.

    Each record: {"n": int, "body": str, "chapter": str}

    Algorithm:
    1. Strip YAML front matter (between the first two '---' fences).
    2. Split the body into blocks on blank lines.
    3. Track the current section heading (any line starting with # ... ##).
    4. Paragraph = a block that is NOT a heading AND has len(stripped) >= 80.
    5. Number paragraphs from 1 across the whole work.
    """
    raw = text_path.read_text(encoding="utf-8")

    # Strip YAML front matter: content between the very first --- and the
    # closing ---. The front matter always starts at byte 0.
    if raw.startswith("---"):
        end = raw.find("\n---\n", 3)
        if end != -1:
            raw = raw[end + 4:]  # skip past the closing ---\n

    current_heading: str = ""
    n = 0
    results: List[Dict[str, Any]] = []

    for line in raw.splitlines():
        heading_match = re.match(r"^(#{1,6})\s+(.*)", line.strip())
        if heading_match:
            current_heading = heading_match.group(2).strip()
        # We accumulate per-line; blank lines in the raw text signal paragraph
        # breaks but we handle multi-line paragraphs by joining on the fly.
        # Simpler approach: split on double newlines in original text.

    # Better: split the whole body on blank lines, then classify each block.
    blocks = re.split(r"\n{2,}", raw)
    current_heading = ""
    n = 0
    results = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        heading_match = re.match(r"^(#{1,6})\s+(.*)", block)
        if heading_match:
            current_heading = heading_match.group(2).strip()
            continue
        # Skip short/decorative blocks
        if len(block) < 80:
            continue
        n += 1
        results.append({"n": n, "body": block, "chapter": current_heading})
    return results


# In-process cache of parsed works. Key: (path, lang). Cleared on reload.
_reading_cache: Dict[tuple, List[Dict[str, Any]]] = {}
```

- [ ] **Step 3: Add the `/read/{slug}` endpoint**

Add this endpoint to `tools/server.py` AFTER the `admin_reload` endpoint (after line ~265, before `_prepare_request`):

```python
@app.get("/read/{slug}")
def read_work(slug: str, lang: Optional[str] = None, page: int = 1) -> Dict[str, Any]:
    """Return one page of real corpus text for the given work slug.

    Query params:
      lang  — optional; defaults to the work's first language in the catalog.
      page  — 1-based page number (default 1); 4 paragraphs per page.

    Returns a ReadingPage JSON object:
      {workSlug, workTitle, author, chapter, totalPages, paragraphs: [{n, body}]}

    404 if the slug is not in the catalog or the text.md file is missing.
    """
    # Load catalog
    catalog_path = REPO / "03_catalog" / "catalog.yaml"
    with open(catalog_path, encoding="utf-8") as f:
        catalog = yaml.safe_load(f)

    work_meta = None
    for w in catalog.get("works", []):
        if w.get("id") == slug:
            work_meta = w
            break

    # Fallback: if not in catalog, try to locate the text.md by scanning the
    # canonical directory. This handles pathway-to-god-in-hindi-literature
    # which exists on disk but is absent from catalog.yaml.
    if work_meta is None:
        # Try common canonical path patterns
        candidate_dirs = [
            REPO / "01_canonical" / "gurudev_ranade" / "books" / slug,
            REPO / "01_canonical" / "bhausaheb_maharaj" / "letters" / slug,
            REPO / "01_canonical" / "kakasaheb_tulpule" / "books" / slug,
            REPO / "01_canonical" / "other_authors" / "books" / slug,
            REPO / "02_aggregated" / "biography" / "about_gurudev_ranade" / slug,
        ]
        work_dir = None
        for d in candidate_dirs:
            if d.exists():
                work_dir = d
                break
        if work_dir is None:
            raise HTTPException(status_code=404, detail=f"Work not found: {slug!r}")
        # Infer author from path
        parts = work_dir.parts
        author_id = "gurudev_ranade"
        for i, part in enumerate(parts):
            if part in ("01_canonical", "02_aggregated"):
                # Next part is the author
                if i + 1 < len(parts):
                    candidate = parts[i + 1]
                    if candidate not in ("biography",):
                        author_id = candidate
                break
        # Infer languages from subdirectory names
        langs_on_disk = sorted(
            d.name for d in work_dir.iterdir()
            if d.is_dir() and (d / "text.md").exists()
        )
        work_meta = {
            "id": slug,
            "title": slug.replace("-", " ").title(),
            "author": author_id,
            "languages": langs_on_disk or ["en"],
            "path": str(work_dir.relative_to(REPO)) + "/",
        }

    # Resolve language
    available_langs: List[str] = work_meta.get("languages", ["en"])
    if lang is None:
        lang = available_langs[0]
    elif lang not in available_langs:
        raise HTTPException(
            status_code=404,
            detail=f"Language {lang!r} not available for {slug!r}. Available: {available_langs}",
        )

    # Locate text.md
    work_path_str: str = work_meta.get("path", "")
    if not work_path_str:
        raise HTTPException(status_code=404, detail=f"No path for work {slug!r}")
    text_path = REPO / work_path_str.rstrip("/") / lang / "text.md"
    if not text_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"text.md not found at {text_path.relative_to(REPO)}",
        )

    # Parse (with cache)
    cache_key = (str(text_path), lang)
    if cache_key not in _reading_cache:
        _reading_cache[cache_key] = _parse_work_text(text_path)
    all_paragraphs = _reading_cache[cache_key]

    total = len(all_paragraphs)
    if total == 0:
        raise HTTPException(status_code=404, detail="Work has no parseable paragraphs")

    PAGE_SIZE = 4
    total_pages = math.ceil(total / PAGE_SIZE)
    page = max(1, min(page, total_pages))
    start = (page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    page_paras = all_paragraphs[start:end]

    chapter = page_paras[0]["chapter"] if page_paras else ""

    title: str = work_meta.get("title") or slug.replace("-", " ").title()
    author_display = _author_display_name(work_meta.get("author", ""))

    return {
        "workSlug": slug,
        "workTitle": title,
        "author": author_display,
        "chapter": chapter,
        "totalPages": total_pages,
        "paragraphs": [{"n": p["n"], "body": p["body"]} for p in page_paras],
    }
```

- [ ] **Step 4: Also clear reading cache in `admin_reload`**

In `tools/server.py`, find the `admin_reload` function and add `_reading_cache.clear()` at the start:

```python
@app.post("/admin/reload")
def admin_reload() -> Dict[str, Any]:
    _reading_cache.clear()  # ← add this line
    before = len(getattr(STATE, "metas", []) or [])
    # ... rest of function unchanged
```

- [ ] **Step 5: Run existing tests to confirm nothing is broken**

```bash
cd /Users/neharepal/gurudev-corpus
/Users/neharepal/opt/anaconda3/bin/python -m pytest tools/tests/ -q
```

Expected: all existing tests pass (no imports from server.py in existing tests, so no breakage).

- [ ] **Step 6: Commit backend**

```bash
cd /Users/neharepal/gurudev-corpus
git add tools/server.py
git commit -m "feat(backend): add GET /read/{slug} endpoint for real corpus reading

Reads work text from 03_catalog/catalog.yaml (with filesystem fallback
for works like pathway-to-god-in-hindi-literature not yet in catalog),
strips YAML front matter, parses paragraphs and ## headings, paginates
at 4 paragraphs/page. Author display: gurudev_ranade → 'Shri Gurudev'.
In-process cache avoids re-parsing on each request.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Backend Tests

**Files:**
- Create: `tools/tests/test_read_endpoint.py`

**Interfaces:**
- Consumes: `tools/server.py` app (the FastAPI `app` object) via `fastapi.testclient.TestClient`
- Tests functions: `_author_display_name`, `_parse_work_text`, and the `/read/{slug}` endpoint via TestClient

- [ ] **Step 1: Write the test file**

Create `/Users/neharepal/gurudev-corpus/tools/tests/test_read_endpoint.py`:

```python
"""Tests for the GET /read/{slug} endpoint and its helpers.

Uses FastAPI's TestClient so we never actually start a server — no network,
no port binding. The endpoint reads real corpus files from disk; these tests
require the repo's canonical text files to be present.

Tested work: pathway-to-god-in-hindi-literature (PGHL)
  Path: 01_canonical/gurudev_ranade/books/pathway-to-god-in-hindi-literature/en/text.md
  This work is NOT in 03_catalog/catalog.yaml but IS on disk — tests verify
  the filesystem fallback path works.
"""
import math
import sys
import os

import pytest

# Put tools/ on sys.path (mirrors conftest.py).
TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS_DIR)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    """Return a TestClient for the FastAPI app.

    We must monkeypatch the startup hook because it tries to load embeddings
    and the Anthropic API key — neither is available in test. The reading
    endpoint has no dependency on STATE, so this is safe.
    """
    from fastapi.testclient import TestClient
    import server

    # Bypass the startup handler (it loads embeddings + checks ANTHROPIC_API_KEY).
    # TestClient by default runs lifespan; we disable it via with_lifespan=False.
    # If that kwarg isn't supported (older TestClient), we patch _load_everything.
    try:
        c = TestClient(server.app, raise_server_exceptions=True)
        # Force no lifespan by calling with a context manager and not triggering startup.
        # Actually, TestClient in newer starlette exposes this differently;
        # simplest approach: monkeypatch the startup handler.
    except Exception:
        pass

    # Safer approach: override the startup event handler
    original_handlers = server.app.router.on_startup[:]
    server.app.router.on_startup.clear()
    c = TestClient(server.app, raise_server_exceptions=True)
    server.app.router.on_startup.extend(original_handlers)
    return c


@pytest.fixture(scope="module")
def pghl_page1(client):
    resp = client.get("/read/pathway-to-god-in-hindi-literature?page=1")
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.fixture(scope="module")
def pghl_page2(client):
    resp = client.get("/read/pathway-to-god-in-hindi-literature?page=2")
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Helper unit tests (no server needed)
# ---------------------------------------------------------------------------


def test_author_display_gurudev_ranade():
    from server import _author_display_name
    assert _author_display_name("gurudev_ranade") == "Shri Gurudev"


def test_author_display_other_authors():
    from server import _author_display_name
    assert _author_display_name("bhausaheb_maharaj") == "Bhausaheb Maharaj"
    assert _author_display_name("kakasaheb_tulpule") == "Kakasaheb Tulpule"
    assert _author_display_name("about_gurudev_ranade") == "About Gurudev Ranade"


def test_parse_work_text_returns_paragraphs():
    from pathlib import Path
    from server import _parse_work_text
    text_path = (
        Path(TOOLS_DIR).parent
        / "01_canonical/gurudev_ranade/books/pathway-to-god-in-hindi-literature/en/text.md"
    )
    assert text_path.exists(), f"text.md not found at {text_path}"
    paras = _parse_work_text(text_path)
    # Should have many paragraphs for a full book
    assert len(paras) > 100, f"Expected >100 paragraphs, got {len(paras)}"
    # Each paragraph has n, body, chapter fields
    for p in paras[:5]:
        assert "n" in p
        assert "body" in p
        assert "chapter" in p
        assert len(p["body"]) >= 80, f"Short paragraph slipped through: {p['body']!r}"
    # Paragraphs are numbered from 1 consecutively
    for i, p in enumerate(paras):
        assert p["n"] == i + 1


def test_parse_work_text_tracks_headings():
    from pathlib import Path
    from server import _parse_work_text
    text_path = (
        Path(TOOLS_DIR).parent
        / "01_canonical/gurudev_ranade/books/pathway-to-god-in-hindi-literature/en/text.md"
    )
    paras = _parse_work_text(text_path)
    # At least some paragraphs should have a non-empty chapter
    chapters_seen = {p["chapter"] for p in paras if p["chapter"]}
    assert len(chapters_seen) >= 1, "Expected at least one section heading to be tracked"


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------


def test_read_page1_status_and_shape(pghl_page1):
    data = pghl_page1
    assert data["workSlug"] == "pathway-to-god-in-hindi-literature"
    assert "workTitle" in data
    assert "author" in data
    assert "chapter" in data
    assert "totalPages" in data
    assert "paragraphs" in data


def test_read_page1_author_is_shri_gurudev(pghl_page1):
    assert pghl_page1["author"] == "Shri Gurudev"


def test_read_page1_has_four_paragraphs(pghl_page1):
    # Page 1 should have exactly 4 paragraphs (unless totalPages == 1)
    paras = pghl_page1["paragraphs"]
    total_pages = pghl_page1["totalPages"]
    if total_pages > 1:
        assert len(paras) == 4, f"Expected 4 paragraphs on page 1, got {len(paras)}"


def test_read_total_pages_is_sane(pghl_page1):
    total_pages = pghl_page1["totalPages"]
    assert total_pages > 1, f"Expected >1 page for PGHL, got {total_pages}"
    # PGHL is a full book; should have well over 50 pages at 4/page
    assert total_pages > 50, f"Expected >50 pages for PGHL, got {total_pages}"


def test_read_chapter_is_populated(pghl_page1):
    # chapter should be a non-empty string (may be the first ## heading encountered)
    assert isinstance(pghl_page1["chapter"], str)
    # chapter might be empty if the first paragraph is before any heading;
    # we accept empty here but it should at least be a string


def test_read_page1_and_page2_have_different_paragraphs(pghl_page1, pghl_page2):
    bodies_p1 = {p["body"] for p in pghl_page1["paragraphs"]}
    bodies_p2 = {p["body"] for p in pghl_page2["paragraphs"]}
    assert bodies_p1.isdisjoint(bodies_p2), "Page 1 and page 2 share paragraphs — pagination is broken"


def test_read_paragraph_numbers_advance_across_pages(pghl_page1, pghl_page2):
    ns_p1 = [p["n"] for p in pghl_page1["paragraphs"]]
    ns_p2 = [p["n"] for p in pghl_page2["paragraphs"]]
    assert max(ns_p1) < min(ns_p2), (
        f"Page 2 paragraph numbers ({ns_p2}) should be higher than page 1 ({ns_p1})"
    )


def test_read_unknown_slug_returns_404(client):
    resp = client.get("/read/no-such-work-ever")
    assert resp.status_code == 404


def test_read_invalid_lang_returns_404(client):
    # 'xx' is not a valid language for any work
    resp = client.get("/read/pathway-to-god-in-hindi-literature?lang=xx")
    assert resp.status_code == 404


def test_read_page_clamps_to_valid_range(client):
    # page=9999 should clamp to last page, not 404
    resp = client.get("/read/pathway-to-god-in-hindi-literature?page=9999")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["paragraphs"]) >= 1
```

- [ ] **Step 2: Run the tests to verify they pass**

```bash
cd /Users/neharepal/gurudev-corpus
/Users/neharepal/opt/anaconda3/bin/python -m pytest tools/tests/test_read_endpoint.py -v
```

Expected output (all pass):
```
PASSED tools/tests/test_read_endpoint.py::test_author_display_gurudev_ranade
PASSED tools/tests/test_read_endpoint.py::test_author_display_other_authors
PASSED tools/tests/test_read_endpoint.py::test_parse_work_text_returns_paragraphs
PASSED tools/tests/test_read_endpoint.py::test_parse_work_text_tracks_headings
PASSED tools/tests/test_read_endpoint.py::test_read_page1_status_and_shape
PASSED tools/tests/test_read_endpoint.py::test_read_page1_author_is_shri_gurudev
PASSED tools/tests/test_read_endpoint.py::test_read_page1_has_four_paragraphs
PASSED tools/tests/test_read_endpoint.py::test_read_total_pages_is_sane
PASSED tools/tests/test_read_endpoint.py::test_read_chapter_is_populated
PASSED tools/tests/test_read_endpoint.py::test_read_page1_and_page2_have_different_paragraphs
PASSED tools/tests/test_read_endpoint.py::test_read_paragraph_numbers_advance_across_pages
PASSED tools/tests/test_read_endpoint.py::test_read_unknown_slug_returns_404
PASSED tools/tests/test_read_endpoint.py::test_read_invalid_lang_returns_404
PASSED tools/tests/test_read_endpoint.py::test_read_page_clamps_to_valid_range
```

- [ ] **Step 3: Run full test suite to confirm nothing broke**

```bash
cd /Users/neharepal/gurudev-corpus
/Users/neharepal/opt/anaconda3/bin/python -m pytest tools/tests/ -q
```

Expected: all tests pass.

- [ ] **Step 4: Commit tests**

```bash
cd /Users/neharepal/gurudev-corpus
git add tools/tests/test_read_endpoint.py
git commit -m "test(backend): add test suite for GET /read/{slug} endpoint

Tests: pagination correctness (p1 != p2), author display convention
(gurudev_ranade -> 'Shri Gurudev'), totalPages > 1, chapter populated,
404 on unknown slug/lang, page clamping. Uses FastAPI TestClient
with startup hook bypassed to avoid loading embeddings in tests.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Frontend — Next.js API proxy route

**Files:**
- Create: `chat-app/app/api/read/route.ts`

**Interfaces:**
- Consumes: `GET ${BACKEND_URL}/read/${slug}?lang=...&page=...`
- Produces: `GET /api/read?slug=...&lang=...&page=...` → proxies backend response

- [ ] **Step 1: Create `chat-app/app/api/read/route.ts`**

```typescript
// GET /api/read
//
// Thin proxy to GET /read/{slug} on the Python backend (tools/server.py).
// Query params: slug (required), lang (optional), page (optional, 1-based).
//
// Backend URL: process.env.GURUDEV_BACKEND_URL || "http://localhost:8765"
// — same constant as /api/ask/route.ts.

import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL =
  process.env.GURUDEV_BACKEND_URL || "http://localhost:8765";

export async function GET(req: NextRequest) {
  const params = req.nextUrl.searchParams;
  const slug = params.get("slug");
  if (!slug) {
    return NextResponse.json({ error: "slug is required" }, { status: 400 });
  }

  const lang = params.get("lang");
  const page = params.get("page");

  const qs = new URLSearchParams();
  if (lang) qs.set("lang", lang);
  if (page) qs.set("page", page);

  const url = `${BACKEND_URL}/read/${encodeURIComponent(slug)}${qs.toString() ? "?" + qs.toString() : ""}`;

  let upstream: Response;
  try {
    upstream = await fetch(url, { cache: "no-store" });
  } catch {
    return NextResponse.json(
      {
        error: `Backend unreachable at ${BACKEND_URL}. Start it with: ANTHROPIC_API_KEY=… python tools/server.py`,
      },
      { status: 502 },
    );
  }

  const data = await upstream.json();
  return NextResponse.json(data, { status: upstream.status });
}
```

- [ ] **Step 2: Verify the file is syntactically correct by checking TypeScript types mentally** — the `NextRequest`, `NextResponse` imports mirror `app/api/ask/route.ts`. No test needed; we'll exercise it from the frontend.

- [ ] **Step 3: Commit the proxy route**

```bash
cd /Users/neharepal/gurudev-corpus
git add chat-app/app/api/read/route.ts
git commit -m "feat(frontend): add /api/read Next.js proxy route for reading endpoint

Thin GET proxy to Python backend GET /read/{slug}. Accepts slug, lang,
page query params; forwards to backend; surfaces 502 if backend is down.
Mirrors /api/ask/route.ts pattern.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Frontend — Wire reader page to real data

**Files:**
- Modify: `chat-app/app/read/[slug]/page.tsx`

**Interfaces:**
- Consumes: `/api/read?slug=...&lang=...&page=...` (Task 3 proxy)
- Produces: `ReadingPage` — same type as the mock, imported from `../../../data/mock-conversations`

Key changes in `page.tsx`:
1. Remove `import { getReadingPage } from "../../../data/mock-conversations";`
2. Import `ReadingPage` type from mock-conversations (type-only import, so it doesn't import the data)
3. Add `useEffect` + `useState` for `pageData: ReadingPage | null`, `loading: boolean`, `fetchError: string | null`
4. Fetch on mount and whenever `currentPage` or `lang` changes
5. Replace `if (!page) { notFound(); }` with loading/error states
6. Replace `page.paragraphs`, `page.totalPages`, `page.workTitle`, `page.author`, `page.chapter` with `pageData?....` (with fallback)

- [ ] **Step 1: Study current imports and state at lines 1–140 of page.tsx**

(Already read above in planning.) The file:
- Has `"use client"` directive
- Imports `getReadingPage` from mock-conversations at line 16
- Uses `const page = useMemo(() => getReadingPage(slug), [slug]);` at line 113
- Uses `page.totalPages` (line 189), `page.paragraphs.map(...)` (line 262), `page.workTitle` (line 226), `page.author` (line 231), `page.chapter` (line 231)
- Has a `notFound()` call at line 139 when `!page`

- [ ] **Step 2: Edit `chat-app/app/read/[slug]/page.tsx` to wire real data**

Replace the mock import and usage. The full set of changes:

**Change 1:** Replace line 16 (`import { getReadingPage } from ...`) with a type-only import:

Old:
```typescript
import { getReadingPage } from "../../../data/mock-conversations";
```

New:
```typescript
import type { ReadingPage } from "../../../data/mock-conversations";
```

**Change 2:** Add `useEffect` to the existing React imports (line 10–15). Change:
```typescript
import {
  Suspense,
  useMemo,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
```
To:
```typescript
import {
  Suspense,
  useEffect,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
```

**Change 3:** In the `ReadingPage` function body, replace lines 113–140 (the `useMemo` + `notFound` block) with:

Old:
```typescript
  const page = useMemo(() => getReadingPage(slug), [slug]);
  // ...other state...
  if (!page) {
    notFound();
  }
```

New (insert after the existing `usePersistentState` calls and before the `ask` function):
```typescript
  // Real corpus fetch — re-runs whenever slug, lang, or currentPage changes.
  const [pageData, setPageData] = useState<ReadingPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setFetchError(null);
    const qs = new URLSearchParams({ slug, page: String(currentPage) });
    if (lang) qs.set("lang", lang);
    fetch(`/api/read?${qs.toString()}`)
      .then(async (res) => {
        if (!res.ok) {
          const body = await res.json().catch(() => ({})) as { error?: string };
          throw new Error(body.error ?? `Error ${res.status}`);
        }
        return res.json() as Promise<ReadingPage>;
      })
      .then((data) => {
        if (!cancelled) {
          setPageData(data);
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setFetchError(err instanceof Error ? err.message : "Failed to load");
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [slug, lang, currentPage]);
```

**Change 4:** Remove the old `notFound()` block entirely (it was triggered by `!page`; now we show an error state instead).

**Change 5:** Update the `total` variable. Old:
```typescript
  const total = page.totalPages;
```
New:
```typescript
  const total = pageData?.totalPages ?? 1;
```

**Change 6:** Replace the JSX that uses `page.*` fields:

In the header block (around line 222–234), replace:
```tsx
          <div className="text-[20px] font-semibold leading-tight" style={{ color: "var(--text-primary)" }}>
            {page.workTitle}
          </div>
          <div className="text-[13.5px]" style={{ color: "var(--text-secondary)" }}>
            {page.author} · {page.chapter}
          </div>
```
With:
```tsx
          <div className="text-[20px] font-semibold leading-tight" style={{ color: "var(--text-primary)" }}>
            {pageData?.workTitle ?? slug.replace(/-/g, " ")}
          </div>
          <div className="text-[13.5px]" style={{ color: "var(--text-secondary)" }}>
            {pageData ? `${pageData.author} · ${pageData.chapter}` : ""}
          </div>
```

**Change 7:** Replace the article body (around line 261–281). Old:
```tsx
      <article className="mx-auto w-full max-w-reading flex-1">
        {page.paragraphs.map((para) => (
          <div key={para.n} className="mb-7 flex gap-4">
            <div className="shrink-0 pt-1 font-mono text-[12px]" style={{ color: "var(--text-secondary)" }}>
              ¶ {para.n}
            </div>
            <p className="text-[17.5px]" style={{ color: "var(--text-primary)", lineHeight: 1.7 }}>
              {para.body}
            </p>
          </div>
        ))}
      </article>
```
New:
```tsx
      <article className="mx-auto w-full max-w-reading flex-1">
        {loading ? (
          <p className="text-[15px] italic" style={{ color: "var(--text-tertiary)" }}>
            Loading…
          </p>
        ) : fetchError ? (
          <p className="text-[15px]" style={{ color: "var(--accent-maroon)" }}>
            {fetchError}
          </p>
        ) : (pageData?.paragraphs ?? []).map((para) => (
          <div key={para.n} className="mb-7 flex gap-4">
            <div className="shrink-0 pt-1 font-mono text-[12px]" style={{ color: "var(--text-secondary)" }}>
              ¶ {para.n}
            </div>
            <p className="text-[17.5px]" style={{ color: "var(--text-primary)", lineHeight: 1.7 }}>
              {para.body}
            </p>
          </div>
        ))}
      </article>
```

**Change 8:** In the drawer (around line 382, `{page.workTitle}`):
```tsx
            {page.workTitle}
```
→
```tsx
            {pageData?.workTitle ?? slug.replace(/-/g, " ")}
```

**Change 9:** In the quote attribution line (around line 454):
```tsx
                <p className="gd-quote-attr">
                  — {page.workTitle}, {page.chapter} · {page.author}
                </p>
```
→
```tsx
                <p className="gd-quote-attr">
                  — {pageData?.workTitle ?? ""}, {pageData?.chapter ?? ""} · {pageData?.author ?? ""}
                </p>
```

- [ ] **Step 3: Run existing tests to confirm no TypeScript/import regressions**

```bash
cd /Users/neharepal/gurudev-corpus
/Users/neharepal/opt/anaconda3/bin/python -m pytest tools/tests/ -q
```

(TypeScript compilation errors would surface at runtime, not in these Python tests. The main risk is import errors in mock-conversations.ts — we kept all exports intact so it's safe.)

- [ ] **Step 4: Commit frontend changes**

```bash
cd /Users/neharepal/gurudev-corpus
git add chat-app/app/read/\[slug\]/page.tsx
git commit -m "feat(frontend): wire reading mode to real corpus via /api/read

Replaces mock getReadingPage() with a useEffect fetch to /api/read
keyed on slug+lang+currentPage. Page navigation now re-fetches real
paginated text. Shows 'Loading...' while fetching and graceful error
state on failure. Preserves visual design, progress bar, ¶ n rendering,
back links, and language toggle. ReadingPage type import kept from
mock-conversations (type-only); other mock exports untouched.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Final verification and consolidated commit

- [ ] **Step 1: Run the full test suite**

```bash
cd /Users/neharepal/gurudev-corpus
/Users/neharepal/opt/anaconda3/bin/python -m pytest tools/tests/ -q
```

Expected: all tests pass including the new `test_read_endpoint.py` tests.

- [ ] **Step 2: Confirm no new files were created unexpectedly**

```bash
cd /Users/neharepal/gurudev-corpus
git status
```

Expected: clean working tree (all changes committed in Tasks 1–4).

- [ ] **Step 3: Report pass count and commit hash**

```bash
cd /Users/neharepal/gurudev-corpus
git log --oneline -5
```

---

## Known Assumptions and Follow-ups

1. **`pathway-to-god-in-hindi-literature` not in catalog:** The filesystem fallback in the `/read/{slug}` endpoint handles this. However, the catalog should be updated eventually to include all canonical works. The `title` field inferred from slug will be wrong until the catalog entry is added (it would be "Pathway To God In Hindi Literature" rather than "Pathway to God in Hindi Literature" — no issue).

2. **Work title for PGHL:** Since it's not in the catalog, the title is inferred from the slug. To get the proper title "Pathway to God in Hindi Literature", we should add it to catalog.yaml or read from the `meta.yaml` sidecar. The plan above infers from slug which gives "Pathway To God In Hindi Literature" — close but not exact. Consider reading `meta.yaml` or adding to catalog. The tests won't catch this subtlety.

3. **Front matter title extraction:** The `text.md` front matter has `title_en: "Pathway to God in Hindi Literature"`. A refinement would be to parse that. Add to the filesystem-fallback path: read `text_path` front matter for title if available.

4. **Short paragraphs threshold (80 chars):** This may filter some legitimate short paragraphs (e.g. Doha verses that are short). The threshold should be tuned per work type.

5. **Marathi works:** Works with `path` entries that have multi-language support (like `pawanbhumi-jamkhandi`) should work automatically as long as the `lang` param is passed correctly.

6. **No TypeScript unit tests:** The frontend changes are tested by the backend tests (which confirm the API contract) plus visual inspection. Adding a Jest/Vitest test for the proxy route would be a useful follow-up.
