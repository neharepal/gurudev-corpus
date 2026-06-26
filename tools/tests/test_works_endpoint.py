"""Tests for the GET /works endpoint.

Uses FastAPI's TestClient with the startup hook bypassed (same pattern as
test_read_endpoint.py) — no network, no embedding model, no API key needed.

The endpoint scans 01_canonical on the filesystem and returns works that
actually have a text.md.  These tests use two well-known works:

  INCLUDED — pathway-to-god-in-hindi-literature
    Path: 01_canonical/gurudev_ranade/books/pathway-to-god-in-hindi-literature/en/text.md
    Has a real text.md; meta.yaml gives the proper title.

  EXCLUDED — pathway-to-god-in-marathi-literature
    The directory does NOT exist in 01_canonical at all, so this slug must
    never appear in the response.
"""

import os
import sys

import pytest

TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS_DIR)


# ---------------------------------------------------------------------------
# Fixture — TestClient with startup bypassed
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    """Return a TestClient for the FastAPI app with the startup hook cleared."""
    from fastapi.testclient import TestClient
    import server

    original_handlers = server.app.router.on_startup[:]
    server.app.router.on_startup.clear()
    # Also clear the in-process works cache so each test run starts fresh.
    server._works_cache = None
    c = TestClient(server.app, raise_server_exceptions=True)
    server.app.router.on_startup.extend(original_handlers)
    return c


@pytest.fixture(scope="module")
def works_response(client):
    resp = client.get("/works")
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Shape tests
# ---------------------------------------------------------------------------


def test_works_response_has_works_key(works_response):
    assert "works" in works_response, "Response must have a 'works' key"
    assert isinstance(works_response["works"], list)


def test_works_items_have_required_fields(works_response):
    works = works_response["works"]
    assert len(works) > 0, "Expected at least one readable work"
    for w in works:
        assert "slug" in w, f"Missing 'slug' in {w}"
        assert "title" in w, f"Missing 'title' in {w}"
        assert "author" in w, f"Missing 'author' in {w}"
        assert "languages" in w, f"Missing 'languages' in {w}"
        assert isinstance(w["languages"], list), f"'languages' must be a list in {w}"
        assert len(w["languages"]) >= 1, f"'languages' must be non-empty in {w}"


def test_works_sorted_by_title(works_response):
    titles = [w["title"].lower() for w in works_response["works"]]
    assert titles == sorted(titles), "Works must be sorted by title (case-insensitive)"


# ---------------------------------------------------------------------------
# Inclusion / exclusion tests
# ---------------------------------------------------------------------------


def test_pghl_is_included(works_response):
    """pathway-to-god-in-hindi-literature has a text.md and must appear."""
    slugs = {w["slug"] for w in works_response["works"]}
    assert "pathway-to-god-in-hindi-literature" in slugs, (
        "pathway-to-god-in-hindi-literature should be in /works "
        "(it has 01_canonical/.../en/text.md)"
    )


def test_pgml_is_excluded(works_response):
    """pathway-to-god-in-marathi-literature has no text.md and must NOT appear."""
    slugs = {w["slug"] for w in works_response["works"]}
    assert "pathway-to-god-in-marathi-literature" not in slugs, (
        "pathway-to-god-in-marathi-literature must NOT be in /works "
        "(its directory is empty / has no text.md)"
    )


def test_mysticism_in_maharashtra_is_included(works_response):
    """mysticism-in-maharashtra has a text.md and should appear."""
    slugs = {w["slug"] for w in works_response["works"]}
    assert "mysticism-in-maharashtra" in slugs, (
        "mysticism-in-maharashtra should be in /works "
        "(it has 01_canonical/gurudev_ranade/books/mysticism-in-maharashtra/en/text.md)"
    )


# ---------------------------------------------------------------------------
# Title quality tests
# ---------------------------------------------------------------------------


def test_pghl_has_correct_title(works_response):
    """Title must come from meta.yaml, not the slug-humanized fallback."""
    pghl = next(
        (w for w in works_response["works"] if w["slug"] == "pathway-to-god-in-hindi-literature"),
        None,
    )
    assert pghl is not None
    # meta.yaml sets title = "Pathway to God in Hindi Literature"
    assert pghl["title"] == "Pathway to God in Hindi Literature", (
        f"Expected proper title from meta.yaml, got {pghl['title']!r}"
    )


def test_gurudev_author_display_name(works_response):
    """Works by gurudev_ranade must display 'Shri Gurudev'."""
    gurudev_works = [
        w for w in works_response["works"]
        if w["slug"] == "pathway-to-god-in-hindi-literature"
    ]
    assert gurudev_works, "PGHL not found"
    assert gurudev_works[0]["author"] == "Shri Gurudev", (
        f"Expected 'Shri Gurudev', got {gurudev_works[0]['author']!r}"
    )


# ---------------------------------------------------------------------------
# Canonical-only test — aggregated dirs must not appear
# ---------------------------------------------------------------------------


def test_no_biography_works(works_response):
    """02_aggregated biography works must not appear (canonical-only per spec)."""
    # These are slugs that only exist under 02_aggregated/biography/...
    # They should not appear because we only scan 01_canonical.
    biography_slugs = {"about_gurudev_ranade", "biography"}
    slugs = {w["slug"] for w in works_response["works"]}
    overlap = biography_slugs & slugs
    assert not overlap, (
        f"Biography slugs should not appear in /works: {overlap}"
    )
