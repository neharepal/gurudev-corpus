"""Tests for the GET /read/{slug} endpoint and its helpers.

Uses FastAPI's TestClient so we never actually start a server — no network,
no port binding. The endpoint reads real corpus files from disk; these tests
require the repo's canonical text files to be present.

Tested work: pathway-to-god-in-hindi-literature (PGHL)
  Path: 01_canonical/gurudev_ranade/books/pathway-to-god-in-hindi-literature/en/text.md
  This work is NOT in 03_catalog/catalog.yaml but IS on disk — tests verify
  the filesystem fallback path works.
"""
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

    # Override the startup event handler to avoid loading embeddings and API key checks
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


def test_read_page1_has_at_most_four_paragraphs(pghl_page1):
    # Pagination is chapter-aware (see pagination.py / RFC 2026-07-03 reading
    # mode book layout): a page holds AT MOST PAGE_SIZE (4) paragraphs, but a
    # chapter boundary always starts a fresh page even with fewer than 4 — so
    # a short front-matter chapter (PGHL's page 1 is "Publishers' Note to the
    # Fourth Edition", 1 paragraph) legitimately yields <4. Assert the upper
    # bound (and non-empty), not exact equality.
    paras = pghl_page1["paragraphs"]
    total_pages = pghl_page1["totalPages"]
    if total_pages > 1:
        assert 1 <= len(paras) <= 4, f"Expected 1-4 paragraphs on page 1, got {len(paras)}"


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


def test_read_invalid_lang_falls_back_to_primary_language(client):
    # Policy change (server.py read_work, ~line 1275): an unavailable/invalid
    # `lang` no longer 404s — it falls back to the work's primary available
    # language. This supports "Read in full" links that carry the UI's
    # language even when the target work only exists in another language.
    resp = client.get("/read/pathway-to-god-in-hindi-literature?lang=xx")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["paragraphs"]) >= 1


def test_read_page_clamps_to_valid_range(client):
    # page=9999 should clamp to last page, not 404
    resp = client.get("/read/pathway-to-god-in-hindi-literature?page=9999")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["paragraphs"]) >= 1
