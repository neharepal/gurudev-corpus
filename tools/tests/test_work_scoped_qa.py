"""Tests for work-scoped Q&A retrieval parameter selection.

We test the _prepare_request logic that decides metadata_filter and
max_per_source without hitting the corpus, the embedding model, or the
Anthropic API. The approach: monkeypatch _retrieve to capture what
parameters it was called with, then assert on those captured values.

Four cases:
  1. mode=qa, no work  → no filter, max_per_source=2
  2. mode=qa, work set  → filter={"work_id": slug}, max_per_source=top_k (12)
  3. mode=reading, work set  → filter={"work_id": slug}, max_per_source=top_k (5)
  4. mode=pravachan, no work  → no filter, max_per_source=2
"""

import os
import sys
from typing import Optional

import pytest

TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS_DIR)


# ---------------------------------------------------------------------------
# Shared fixture: capture _retrieve call params without loading a corpus.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def patch_retrieve_and_llm(monkeypatch):
    """Replace _retrieve and STATE.client.ask_structured with stubs.

    _retrieve → records the kwargs it was called with and returns one
    fake chunk so _prepare_request doesn't raise 404.

    We don't exercise the LLM path here — just the retrieval param selection.
    """
    import server

    captured = {}

    def fake_retrieve(question, *, top_k, candidates, mmr_lambda,
                      max_per_source, metadata_filter=None):
        captured["top_k"] = top_k
        captured["max_per_source"] = max_per_source
        captured["metadata_filter"] = metadata_filter
        # Return one minimal fake chunk so _prepare_request doesn't 404.
        return [
            {
                "meta": {
                    "work_id": "some-work",
                    "title": "Some Work",
                    "kind": "canonical",
                    "language": "en",
                    "char_start": 0,
                },
                "text": "A short passage.",
                "cos_score": 0.9,
                "mmr_score": 0.85,
            }
        ]

    monkeypatch.setattr(server, "_retrieve", fake_retrieve)
    return captured


# ---------------------------------------------------------------------------
# Helper: build an AskRequest and call _prepare_request.
# ---------------------------------------------------------------------------


def _run(mode: str, work: Optional[str] = None):
    """Call server._prepare_request and return the captured retrieve kwargs."""
    import server

    # Access the fixture via the monkeypatching that already ran.
    # We need to import *after* the monkeypatch fixture has applied.
    req = server.AskRequest(
        mode=mode,
        question="What does this work say about bhakti?",
        lang="en",
        work=work,
    )
    # _prepare_request calls _retrieve internally; we capture params there.
    # It also tries to build a prompt — that's fine, no LLM call happens.
    server._prepare_request(req)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_qa_no_work_has_no_filter_and_single_chunk_cap(patch_retrieve_and_llm):
    """Unscoped Q&A: no metadata_filter, max_per_source==2 (drifted from 1)."""
    _run(mode="qa", work=None)
    captured = patch_retrieve_and_llm
    assert captured["metadata_filter"] is None, (
        "Unscoped Q&A must not apply a work filter"
    )
    assert captured["max_per_source"] == 2, (
        "Unscoped Q&A must cap at 2 chunks per source for corpus breadth"
    )


def test_qa_with_work_applies_filter_and_full_top_k(patch_retrieve_and_llm):
    """Work-scoped Q&A: filter={"work_id": slug}, max_per_source==top_k (12)."""
    _run(mode="qa", work="pathway-to-god-in-hindi-literature")
    captured = patch_retrieve_and_llm
    assert captured["metadata_filter"] == {
        "work_id": "pathway-to-god-in-hindi-literature"
    }, "Work-scoped Q&A must set work_id filter"
    # top_k for qa is 12; with a work filter max_per_source must equal top_k
    assert captured["max_per_source"] == captured["top_k"], (
        "Work-scoped Q&A must allow top_k chunks from the single filtered work"
    )
    assert captured["top_k"] == 12, "Q&A top_k must be 12"


def test_reading_with_work_applies_filter_and_full_top_k(patch_retrieve_and_llm):
    """Reading mode (original path): filter applied, max_per_source==top_k (5)."""
    _run(mode="reading", work="pathway-to-god-in-hindi-literature")
    captured = patch_retrieve_and_llm
    assert captured["metadata_filter"] == {
        "work_id": "pathway-to-god-in-hindi-literature"
    }
    assert captured["max_per_source"] == captured["top_k"]
    assert captured["top_k"] == 5, "Reading top_k must be 5"


def test_pravachan_no_work_has_no_filter_and_cap_of_two(patch_retrieve_and_llm):
    """Pravachan: no filter, max_per_source==2."""
    _run(mode="pravachan", work=None)
    captured = patch_retrieve_and_llm
    assert captured["metadata_filter"] is None
    assert captured["max_per_source"] == 2


def test_qa_work_scoped_max_per_source_equals_top_k_not_one(patch_retrieve_and_llm):
    """Regression guard: work-scoped Q&A must NOT keep the breadth cap of 1.

    Before the fix, max_per_source for QA was always 1 regardless of whether
    a work filter was set. This test pins the corrected behaviour.
    """
    _run(mode="qa", work="some-work-slug")
    captured = patch_retrieve_and_llm
    assert captured["max_per_source"] != 1, (
        "Work-scoped Q&A must not use the corpus-breadth cap of 1 — "
        "that would return only one chunk from the filtered work."
    )
    assert captured["max_per_source"] == captured["top_k"]
