"""Regression: `verify_arthasahit_ingest._has_artha_header` must match the
same boundary the parser uses (`arthasahit_parse._ARTHA_RE`). If the two
drift, the verifier flags cases the parser correctly kept in the verse
(false positives) — 2026-07-18 saw 40 legitimate tukaram-vachanamrut
verses mis-flagged because the verifier's substring check triggered on
`अर्थात्` / `अर्थ` as a common Marathi noun/adverb.

The RIGHT marker is a paragraph-initial `अर्थ` NOT followed by another
Devanagari letter — a heading like `अर्थ -`, `अर्थ :`, `अर्थ १`. Anything
in the middle of a sentence (including `अर्थात्`, `अर्थपूर्ण`,
`अर्थाची`, `श्लोकाचा अर्थ`) is a legitimate content occurrence and must
NOT be flagged.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from verify_arthasahit_ingest import _has_artha_header  # noqa: E402
from arthasahit_parse import _ARTHA_RE  # noqa: E402


# ── True positives (headings that ARE the meaning-gloss marker) ──────────

def test_line_start_bare_arthasahit_header():
    """The canonical form — a line beginning with `अर्थ` and a dash."""
    text = "काही तत्त्व - काही ओळ\nअर्थ - असे आहे की..."
    assert _has_artha_header(text)


def test_arthasahit_header_with_colon():
    text = "verse content\nअर्थ : meaning follows"
    assert _has_artha_header(text)


def test_arthasahit_header_with_leading_whitespace():
    """Some sources indent the meaning heading — still counts."""
    text = "verse\n    अर्थ - meaning"
    assert _has_artha_header(text)


def test_arthasahit_header_followed_by_devanagari_digit():
    """Devanagari digits (०-९, U+0966-U+096F) are also in the ऀ-ॿ block, so
    a plain negative-lookahead would reject `अर्थ १`. Verify this actually
    matches — the parser accepts it because it uses `.*` after."""
    # This depends on the exact regex; verify against the parser directly.
    text = "verse\nअर्थ १. explanation"
    parser_matches = bool(_ARTHA_RE.search(text))
    verifier_matches = _has_artha_header(text)
    # The two MUST agree.
    assert parser_matches == verifier_matches, \
        f"parser={parser_matches} verifier={verifier_matches} — must match"


# ── False positives that the naive substring check produced 2026-07-18 ──

def test_arthaat_as_adverb_is_not_a_header():
    """The Marathi adverb `अर्थात्` / `अर्थात` means "that is". Legit content."""
    for text in [
        "यासाठी माझी आवडीची जागा, अर्थात विषयांची आवड सोडून मी आलो आहे",
        "अर्थात कृपेचा वर्षाव आहेस",
        "अर्थात स्वर्गच माझ्या घरी अवतरला आहे",
    ]:
        assert not _has_artha_header(text), text


def test_artha_as_noun_meaning_meaning():
    """Common Marathi/Sanskrit noun. Should NOT be flagged."""
    for text in [
        "श्लोकाचा अर्थ – कल्पान्त आला की महाप्रलय होतो",
        "बोल लावण्यात काही अर्थ नाही",
        "महावाक्याचा अर्थ लक्षात घेतला तर",
        "त्यांनाच त्याचा अर्थ समजेल",
        "ओव्यांचा अर्थ, श्री सोनोपंत दांडेकर यांच्या",
    ]:
        assert not _has_artha_header(text), text


def test_artha_compound_words():
    """`अर्थपूर्ण`, `अर्थाची`, `अर्थाने` etc. — legitimate compounds."""
    for text in [
        "अर्थपूर्ण सांगणे झाले",
        "त्या अर्थाची व्याप्ती",
        "अर्थाने ते तसेच म्हणतात",
    ]:
        assert not _has_artha_header(text), text


def test_empty_and_none_input():
    assert not _has_artha_header("")
    assert not _has_artha_header(None)


# ── Cross-check: verifier must MIRROR the parser ────────────────────────

def test_verifier_regex_mirrors_parser_regex_source():
    """The verifier's regex source must match the parser's exactly on the
    boundary — same anchor (`(?m)^\\s*`), same literal (`अर्थ`), same
    lookahead (`(?![ऀ-ॿ])`). The parser adds `.*` to capture the rest of
    the line; the verifier only needs to detect presence, so it stops
    after the lookahead. Assert the two regexes agree on the shared
    boundary bytes."""
    from verify_arthasahit_ingest import _ARTHA_HEADER_RE as V
    parser_src = _ARTHA_RE.pattern
    verifier_src = V.pattern
    # Shared prefix through the lookahead:
    shared = r"(?m)^\s*अर्थ(?![ऀ-ॿ])"
    assert parser_src.startswith(shared), f"parser regex drifted: {parser_src!r}"
    assert verifier_src == shared, f"verifier regex drifted: {verifier_src!r}"
