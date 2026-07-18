"""ADR-018 — unit tests for `query_understanding.extract_mentioned_work`.

Two deterministic tiers, no LLM:

  Tier 1 — QUOTED: any double-quoted span in the query is a hard title
    claim. Bidirectional case-insensitive substring match against
    title / title_en / title_translit. Exactly one work → scope,
    method="quoted".

  Tier 2 — SUBSTRING (unquoted, ≥8 chars): current behavior, kept for
    natural-phrasing queries where the user types the title inline
    without quoting it.

Gold:
  1. Quoted title → scope, method="quoted".
  2. Partial quoted title ("Amar Sandesh") → scope on the unique match.
  3. Devanagari quoted title in a Devanagari query → scope.
  4. Smart quotes (" ") behave identically to straight quotes.
  5. Quoted string that matches multiple works → ambiguous, no scope.
  6. Quoted string that matches nothing → falls through to substring tier.
  7. Substring pass still fires on natural-phrasing (unquoted) queries.
  8. Bhakti-style topical query → no scope (this is the ADR-018 regression).
  9. Apostrophes in "Gurudev's" are NOT parsed as quotes.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import query_understanding as qu  # noqa: E402


_WORKS = [
    {"work_id": "amar-sandesh-sudha", "title": "Amar Sandesh Sudha",
     "title_en": "Amar Sandesh Sudha", "title_translit": ""},
    {"work_id": "sadhakbodh", "title": "Sadhak-Bodh",
     "title_en": "Sadhak-Bodh", "title_translit": ""},
    {"work_id": "parmartha-sopan", "title": "Parmartha Sopan",
     "title_en": "Parmartha Sopan", "title_translit": ""},
    {"work_id": "pathway-to-god-in-hindi-literature",
     "title": "Pathway to God in Hindi Literature",
     "title_en": "Pathway to God in Hindi Literature", "title_translit": ""},
    {"work_id": "pathway-to-god-in-kannada-literature",
     "title": "Pathway to God in Kannada Literature",
     "title_en": "Pathway to God in Kannada Literature", "title_translit": ""},
    {"work_id": "charitra-tatvajnan-tulpule",
     "title": "Gurudev R. D. Ranade — Charitra va Tatvajnan (Life and Philosophy, by S. G. Tulpule)",
     "title_en": "Life and Philosophy",
     "title_translit": "Charitra va Tatvajnan"},
    {"work_id": "vedant", "title": "Vedant",  # 6 chars — short-tier threshold
     "title_en": "Vedant", "title_translit": ""},
    {"work_id": "punyasmruti", "title": "पुण्यस्मृती",
     "title_en": "Punyasmruti", "title_translit": ""},
]


# ── Tier 1: quoted ─────────────────────────────────────────────────────────

def test_quoted_exact_title_scopes():
    r = qu.extract_mentioned_work(
        'What are the key messages in "Amar Sandesh Sudha"?', _WORKS,
    )
    assert r is not None
    assert r["work_id"] == "amar-sandesh-sudha"
    assert r["method"] == "quoted"


def test_quoted_partial_title_scopes_on_unique_match():
    """'Amar Sandesh' is a substring of only one work's title, so
    the bidirectional match settles it."""
    r = qu.extract_mentioned_work(
        'What is in "Amar Sandesh" about namasmarana?', _WORKS,
    )
    assert r is not None
    assert r["work_id"] == "amar-sandesh-sudha"
    assert r["method"] == "quoted"


def test_quoted_devanagari_title_in_devanagari_query():
    r = qu.extract_mentioned_work(
        'गुरुदेव "पुण्यस्मृती" या ग्रंथात काय म्हणतात?', _WORKS,
    )
    assert r is not None
    assert r["work_id"] == "punyasmruti"
    assert r["method"] == "quoted"


def test_quoted_transliteration_matches_translit_field():
    """User quotes the transliteration ("Charitra va Tatvajnan") — the
    match hits the `title_translit` field for charitra-tatvajnan-tulpule."""
    r = qu.extract_mentioned_work(
        'What does "Charitra va Tatvajnan" say about Bhausaheb?', _WORKS,
    )
    assert r is not None
    assert r["work_id"] == "charitra-tatvajnan-tulpule"
    assert r["method"] == "quoted"


def test_smart_quotes_behave_like_straight_quotes():
    r = qu.extract_mentioned_work(
        "What is in “Amar Sandesh Sudha”?", _WORKS,
    )
    assert r is not None
    assert r["method"] == "quoted"
    assert r["work_id"] == "amar-sandesh-sudha"


def test_quoted_short_title_still_scopes():
    """The ≥8-char threshold is a SUBSTRING-tier safeguard (short titles
    collide with topical words when unquoted). A user who explicitly
    quotes `"Vedant"` has expressed intent; scope."""
    r = qu.extract_mentioned_work(
        'Passages from "Vedant" on adhyatma', _WORKS,
    )
    assert r is not None
    assert r["work_id"] == "vedant"
    assert r["method"] == "quoted"


def test_quoted_ambiguous_returns_ambiguous_no_scope():
    """Two quoted titles — user is comparing. Do NOT scope."""
    r = qu.extract_mentioned_work(
        'Compare "Amar Sandesh Sudha" with "Sadhak-Bodh".', _WORKS,
    )
    assert r is not None
    assert r["method"] == "ambiguous"
    assert set(r["candidates"]) == {"amar-sandesh-sudha", "sadhakbodh"}
    assert r["work_id"] is None


def test_quoted_no_match_falls_through_to_substring():
    """Quoted string doesn't match any known title. Substring tier is
    then given a chance — and if it too finds nothing, no scope."""
    r = qu.extract_mentioned_work(
        'What does "some unknown reference" mean?', _WORKS,
    )
    assert r is None


def test_quoted_no_match_but_substring_match_still_scopes():
    """Quoted phrase doesn't match; but the query ALSO names a work
    inline (unquoted). Substring tier catches it."""
    r = qu.extract_mentioned_work(
        'The phrase "adhi tu maga mi" in Pathway to God in Kannada Literature',
        _WORKS,
    )
    assert r is not None
    assert r["work_id"] == "pathway-to-god-in-kannada-literature"
    assert r["method"] == "substring"


def test_apostrophe_in_gurudevs_is_not_parsed_as_quote():
    """"Gurudev's views" would break if we treated single-quotes as
    quotation marks. Regression test — only double quotes are quotes."""
    r = qu.extract_mentioned_work(
        "What are Gurudev's views on bhakti?", _WORKS,
    )
    assert r is None


# ── Tier 2: substring (unchanged behavior, kept for backwards-compat) ─────

def test_substring_exact_title_english():
    r = qu.extract_mentioned_work(
        "What are the key messages in Amar Sandesh Sudha?", _WORKS,
    )
    assert r is not None
    assert r["work_id"] == "amar-sandesh-sudha"
    assert r["method"] == "substring"


def test_substring_hyphenated_title():
    r = qu.extract_mentioned_work("What is in Sadhak-Bodh?", _WORKS)
    assert r is not None
    assert r["work_id"] == "sadhakbodh"
    assert r["method"] == "substring"


def test_substring_devanagari_title_in_devanagari_query():
    r = qu.extract_mentioned_work(
        "पुण्यस्मृती पुस्तकातील मुख्य आठवणी", _WORKS,
    )
    assert r is not None
    assert r["work_id"] == "punyasmruti"
    assert r["method"] == "substring"


def test_substring_case_insensitive():
    r = qu.extract_mentioned_work(
        "what does amar sandesh sudha say", _WORKS,
    )
    assert r is not None
    assert r["work_id"] == "amar-sandesh-sudha"


def test_substring_longest_title_wins():
    r = qu.extract_mentioned_work(
        "What is in Pathway to God in Kannada Literature about bhakti?",
        _WORKS,
    )
    assert r is not None
    assert r["work_id"] == "pathway-to-god-in-kannada-literature"


def test_substring_short_title_below_threshold_ignored():
    """`Vedant` (6 chars) is filtered — matches 'Vedanta' topically."""
    r = qu.extract_mentioned_work(
        "What are Gurudev's views on Vedanta?", _WORKS,
    )
    assert r is None


def test_substring_multiple_distinct_titles_ambiguous():
    r = qu.extract_mentioned_work(
        "Compare Pathway to God in Hindi Literature and Parmartha Sopan.",
        _WORKS,
    )
    assert r is not None
    assert r["method"] == "ambiguous"
    assert "pathway-to-god-in-hindi-literature" in r["candidates"]
    assert "parmartha-sopan" in r["candidates"]


# ── ADR-018 regression: topical queries must NEVER scope ──────────────────

def test_bhakti_regression_no_scope():
    """The 2026-07-18 misfire. The pre-revision LLM fallback picked
    charitra-tatvajnan-tulpule because it matched 'views' → 'Life and
    Philosophy'. The new design has no LLM tier at all, so any
    hypothetical regression here would surface as a substring-tier
    misfire — which requires an actual title in the query, which this
    query does not contain."""
    r = qu.extract_mentioned_work(
        "What are Gurudev's views on Bhakti?", _WORKS,
    )
    assert r is None


def test_no_scope_on_topical_patterns():
    topicals = [
        "What are Gurudev's teachings on karma yoga?",
        "How does Gurudev approach namasmarana?",
        "What does Gurudev say about the nature of the guru?",
        "गुरुदेवांच्या मते ईश्वरप्राप्ती कशी होते?",
        "Explain the Nimbargi sampradaya's stance on ritual worship",
        "What is bhakti?",
        "Who was Bhausaheb Maharaj?",
    ]
    for q in topicals:
        assert qu.extract_mentioned_work(q, _WORKS) is None, q


def test_empty_query_returns_none():
    assert qu.extract_mentioned_work("", _WORKS) is None
    assert qu.extract_mentioned_work("   ", _WORKS) is None


def test_empty_known_works_returns_none():
    assert qu.extract_mentioned_work("Anything", []) is None
    assert qu.extract_mentioned_work("Anything", None) is None
