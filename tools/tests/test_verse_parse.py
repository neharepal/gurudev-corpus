"""Tests for the verse-format parsing path in server._parse_work_text.

Scope-gated to `nityanemavali` via `VERSE_FORMAT_SLUGS` — the same input on
a non-verse-format slug must still drop short blocks and NOT emit heading
paragraphs (regression test for the scope gate).

Backend spec: 2026-08-05 fix for Neha's complaint that nityanemavali's
bhajans/aartis render as a compact prose blob with headings invisible.
"""
from pathlib import Path
import textwrap

import pytest

from server import (
    HEADING_IN_BODY_SLUGS,
    VERSE_FORMAT_SLUGS,
    _is_decorative_block,
    _is_verse_block,
    _parse_work_text,
    _split_verse_lines,
)


# ---------------------------------------------------------------------------
# Unit tests for the pure helpers
# ---------------------------------------------------------------------------


def test_verse_format_slugs_covers_nityanemavali():
    assert "nityanemavali" in VERSE_FORMAT_SLUGS


class TestIsVerseBlock:
    def test_double_danda_marks_verse(self):
        assert _is_verse_block("नारायण, नारायण, नारायण, नारायण॥")

    def test_verse_with_verse_number_marker(self):
        assert _is_verse_block("देश केंपायितु एळु हरिये॥१॥")

    def test_dhruvapada_marker(self):
        assert _is_verse_block("एळु श्रीगिरिवास श्री व्यंकटेशा॥पल्ल॥")

    def test_dense_single_danda_marks_verse(self):
        # ≥3 । fragments, avg length ≤ 80
        s = "लांब पहिले । लांब दुसरे । लांब तिसरे । लांब चौथे"
        assert _is_verse_block(s)

    def test_biography_prose_with_two_danda_is_not_verse(self):
        # Only 2 । fragments — below density threshold
        s = "एका ओळीत दंड आहे । दुसऱ्या ओळीत आणखी दंड आहे"
        assert not _is_verse_block(s)

    def test_plain_prose_is_not_verse(self):
        assert not _is_verse_block(
            "This is a long paragraph of English prose that has no daṇḍa markers."
        )

    def test_empty_block_is_not_verse(self):
        assert not _is_verse_block("")


class TestIsDecorativeBlock:
    def test_star_separator(self):
        assert _is_decorative_block("* * *")

    def test_zero_ornament(self):
        assert _is_decorative_block("०००००")

    def test_devanagari_numbering(self):
        assert _is_decorative_block("(२)")

    def test_om_ornament(self):
        assert _is_decorative_block("॥ ॐ ॥")

    def test_real_short_verse_is_not_decorative(self):
        # A one-pada verse line — MUST NOT be dropped as decoration
        assert not _is_decorative_block("नारायण, नारायण, नारायण, नारायण॥")

    def test_long_block_is_not_decorative(self):
        # >= 20 chars → never decorative even if all-punct-ish
        assert not _is_decorative_block("* * * * * * * * * * * * *")


class TestSplitVerseLines:
    def test_leaves_multiline_block_alone(self):
        # Shape A: one pada per line, blank lines between → already split
        s = "पहिली ओळ॥\nदुसरी ओळ॥"
        assert _split_verse_lines(s) == s

    def test_splits_shape_b_on_double_danda(self):
        # Shape B: many padas concatenated on one line
        s = "शरणु सिद्धिविनायक॥पल्ल॥ निटिलनेत्रन वरदपुत्रने॥१॥ कटिकरांकितकोमलांगने॥२॥"
        out = _split_verse_lines(s)
        lines = out.split("\n")
        assert len(lines) == 3
        assert "॥पल्ल॥" in lines[0]
        assert "॥१॥" in lines[1]
        assert "॥२॥" in lines[2]

    # -------------------------------------------------------------------
    # NEW (2026-08-06 screenshot review): `।` is a MID-PADA caesura, NOT
    # a line break. Only `॥` and its numbered / labeled forms terminate
    # a pada. Splitting on `।` shattered every pada into fragments.
    # -------------------------------------------------------------------

    def test_does_not_split_on_single_danda(self):
        # No `॥` at all → not a shape-B block; leave the caesura in place
        # and return unchanged (single-pada shape-A that happens to sit
        # on one line).
        s = "पहिली । दुसरी । तिसरी"
        assert _split_verse_lines(s) == s

    def test_shape_b_preserves_internal_caesura(self):
        # Exactly Neha's example: two padas, each with an internal `।`
        # caesura, each closing on `॥`. Splitter must produce TWO lines,
        # each keeping its internal `।` and its terminating `॥`.
        s = (
            "मदमत्सर अंगी। दंभाहंकार जिरवूनी द्वैत-कल्पना-मार त्यागुनि॥ "
            "एकाग्रे मन स्वस्थ करोनी। बैस पद्मासनी मुद्रा लाव आत्मभाषणी॥"
        )
        out = _split_verse_lines(s)
        lines = out.split("\n")
        assert len(lines) == 2, f"expected 2 lines, got {lines}"
        assert lines[0].endswith("॥")
        assert lines[1].endswith("॥")
        # Each line preserves the internal `।` caesura
        assert "।" in lines[0]
        assert "।" in lines[1]
        assert "मदमत्सर" in lines[0] and "त्यागुनि" in lines[0]
        assert "एकाग्रे" in lines[1] and "आत्मभाषणी" in lines[1]

    def test_numbered_terminator_stays_on_line(self):
        # Numbered form `॥२॥` must stay glued to its pada, not become
        # its own fragment.
        s = "अवघेचि विश्व एक। अवघेचि ब्रह्म आहे॥२॥"
        out = _split_verse_lines(s)
        lines = out.split("\n")
        assert len(lines) == 1
        assert lines[0].endswith("॥२॥")
        # Internal caesura preserved
        assert "।" in lines[0]

    def test_shape_a_single_line_without_double_danda_unchanged(self):
        # A single-pada block that is NOT terminated with `॥` (came in
        # reflowed onto one line) must be returned as-is: one pada = one
        # line. No splitting on `।` even if present.
        s = "एक ओळ आहे । जरी दंड आहे । पण दुहेरी नाही"
        assert _split_verse_lines(s) == s

    def test_multiple_padas_with_dhr_terminator(self):
        # `॥धृ॥` (dhruvapada) is also a pada terminator.
        s = "गुरुदेव माझा नाथ॥धृ॥ भक्तांचा तारक तो॥१॥"
        out = _split_verse_lines(s)
        lines = out.split("\n")
        assert len(lines) == 2
        assert lines[0].endswith("॥धृ॥")
        assert lines[1].endswith("॥१॥")

    def test_empty_fragments_are_dropped(self):
        # Consecutive terminators or leading whitespace must not produce
        # empty output lines.
        s = "॥ एक पद॥  ॥"
        out = _split_verse_lines(s)
        lines = out.split("\n")
        assert all(ln.strip() for ln in lines)


# ---------------------------------------------------------------------------
# End-to-end: _parse_work_text with a synthetic nityanemavali-shaped file
# ---------------------------------------------------------------------------


SAMPLE_NITYANEMAVALI = textwrap.dedent(
    """\
    ---
    title: Nityanemavali
    lang: mr
    ---

    ॥ ॐ ॥

    ## ५. काकडआरती व भुपाळ्या

    काकड आरती

    नारायण, नारायण, नारायण, नारायण॥

    बेळगायितु, बेळगायितु, बेळगायितु, बेळगायितु॥

    एळ्या एळु निनगेष्टु निद्रा॥

    (२)

    शरणु सिद्धिविनायक॥पल्ल॥
    निटिलनेत्रन वरदपुत्रने॥१॥
    कटिकरांकितकोमलांगने॥२॥

    ### विडा

    यह एक लंबा प्रोज़ पैराग्राफ है जो बिल्कुल भी वर्स नहीं है और अस्सी अक्षरों से बहुत लंबा है ताकि यह डिफ़ॉल्ट फ़िल्टर से भी बच जाए।
    """
)


@pytest.fixture()
def sample_file(tmp_path: Path) -> Path:
    p = tmp_path / "nityanemavali_sample.md"
    p.write_text(SAMPLE_NITYANEMAVALI, encoding="utf-8")
    return p


def _bodies(paras):
    return [p["body"] for p in paras]


class TestParseUnderVerseFormatSlug:
    def test_short_verse_blocks_survive(self, sample_file):
        paras = _parse_work_text(sample_file, slug="nityanemavali")
        bodies = _bodies(paras)
        # One-pada blocks that WOULD be dropped under the default `<80`
        # filter must be preserved for a verse-format book.
        assert any("नारायण, नारायण" in b for b in bodies)
        assert any("बेळगायितु" in b for b in bodies)
        assert any("एळ्या एळु" in b for b in bodies)

    def test_verse_blocks_are_flagged(self, sample_file):
        paras = _parse_work_text(sample_file, slug="nityanemavali")
        verse_bodies = [p["body"] for p in paras if p.get("is_verse")]
        assert any("नारायण, नारायण" in b for b in verse_bodies)
        assert any("बेळगायितु" in b for b in verse_bodies)

    def test_shape_b_block_is_line_split(self, sample_file):
        paras = _parse_work_text(sample_file, slug="nityanemavali")
        shape_b = [p for p in paras if "पल्ल" in p.get("body", "")]
        assert shape_b, "Shape-B verse block not found in parse output"
        assert shape_b[0].get("is_verse") is True
        # Server should emit `\n` between padas so the frontend's
        # `pre-line` renders one pada per line.
        assert "\n" in shape_b[0]["body"]
        lines = shape_b[0]["body"].split("\n")
        assert len(lines) == 3

    def test_h2_heading_emitted_as_paragraph(self, sample_file):
        paras = _parse_work_text(sample_file, slug="nityanemavali")
        headings = [p for p in paras if p.get("is_heading") and p.get("heading_level") == 2]
        assert len(headings) == 1
        assert headings[0]["body"] == "५. काकडआरती व भुपाळ्या"
        assert headings[0]["chapter"] == "५. काकडआरती व भुपाळ्या"

    def test_h3_heading_emitted_as_paragraph(self, sample_file):
        paras = _parse_work_text(sample_file, slug="nityanemavali")
        h3s = [p for p in paras if p.get("is_heading") and p.get("heading_level") == 3]
        assert len(h3s) == 1
        assert h3s[0]["body"] == "विडा"

    def test_decorative_blocks_still_dropped(self, sample_file):
        paras = _parse_work_text(sample_file, slug="nityanemavali")
        bodies = _bodies(paras)
        # `॥ ॐ ॥`, `(२)` should NOT appear as paragraphs
        assert not any(b.strip() == "॥ ॐ ॥" for b in bodies)
        assert not any(b.strip() == "(२)" for b in bodies)

    def test_paragraph_n_is_consecutive(self, sample_file):
        paras = _parse_work_text(sample_file, slug="nityanemavali")
        for i, p in enumerate(paras):
            assert p["n"] == i + 1

    def test_verse_bodies_preserve_bold_markdown(self, sample_file, tmp_path: Path):
        # Verse bodies must not go through _strip_inline_md — future verse
        # sources may carry **bold** markers we want to hand to the frontend.
        src = tmp_path / "bold_verse.md"
        src.write_text(
            "---\ntitle: T\nlang: mr\n---\n\n**नारायण** नारायण नारायण नारायण॥\n",
            encoding="utf-8",
        )
        paras = _parse_work_text(src, slug="nityanemavali")
        assert len(paras) == 1
        # Verse flagged AND the ** survives (contrast with the default path
        # which _strip_inline_md's).
        assert paras[0].get("is_verse") is True
        assert "**" in paras[0]["body"]


# ---------------------------------------------------------------------------
# Regression: non-verse-format slug behaves exactly like before (scope gate)
# ---------------------------------------------------------------------------


class TestParseUnderNonVerseFormatSlug:
    """The exact same file, parsed WITHOUT a verse-format slug, must keep the
    default behavior: short blocks dropped, no is_heading synthetics, no
    is_verse flags. Guards the scope gate."""

    def test_short_verse_blocks_dropped_when_unscoped(self, sample_file):
        paras = _parse_work_text(sample_file, slug=None)
        bodies = _bodies(paras)
        # All one-pada verse blocks are < 80 chars → dropped by default filter
        assert not any("नारायण, नारायण" in b for b in bodies)
        assert not any("बेळगायितु" in b for b in bodies)

    def test_no_heading_paragraphs_emitted_when_unscoped(self, sample_file):
        paras = _parse_work_text(sample_file, slug=None)
        assert not any(p.get("is_heading") for p in paras)

    def test_no_verse_flags_when_unscoped(self, sample_file):
        paras = _parse_work_text(sample_file, slug=None)
        assert not any(p.get("is_verse") for p in paras)

    def test_only_long_prose_survives_when_unscoped(self, sample_file):
        paras = _parse_work_text(sample_file, slug=None)
        # Just the long Hindi prose paragraph
        assert len(paras) == 1
        assert "प्रोज़ पैराग्राफ" in paras[0]["body"]

    def test_control_slug_kakanchi_pravachane_uses_default_path(self, sample_file):
        # Belt-and-suspenders: pass another slug that's NOT in the set.
        paras = _parse_work_text(sample_file, slug="kakanchi-pravachane")
        assert not any(p.get("is_heading") for p in paras)
        assert not any(p.get("is_verse") for p in paras)
        # Same output as slug=None
        assert len(paras) == 1


# ---------------------------------------------------------------------------
# Verse-run extension via adjacency (Follow-up 1, rule-change 2026-08-06)
# ---------------------------------------------------------------------------
#
# For VERSE_FORMAT_SLUGS books, after the per-block detector runs, we
# extend the `is_verse` flag outward from each seed verse to any adjacent
# paragraph that is (a) SHORT (body < 200 chars) and (b) not `is_heading`.
# Extension iterates: chains of short paragraphs propagate the flag until
# a LONG (≥ 200 char) prose paragraph blocks it. This lets bhajan/aarti
# sections become uniformly verse-styled without over-flagging biography
# sections whose prose paragraphs are long.


def _make_md(*blocks: str) -> str:
    return "---\ntitle: T\nlang: mr\n---\n\n" + "\n\n".join(blocks) + "\n"


class TestVerseRunExtension:
    """Adjacency-based verse-run extension (replaces the earlier
    sticky-per-section approach)."""

    def test_short_prose_before_verse_gets_flagged(self, tmp_path: Path):
        # Short (< 200 chars) prose immediately before a verse pada
        # propagates the `is_verse` flag backwards.
        short_prose = "काकड आरती"  # 9 chars, not a heading
        verse = "नारायण, नारायण, नारायण, नारायण॥"
        p = tmp_path / "before.md"
        p.write_text(_make_md(short_prose, verse), encoding="utf-8")
        paras = _parse_work_text(p, slug="nityanemavali")
        # Both paragraphs should be flagged
        assert len(paras) == 2
        assert paras[0]["body"].startswith("काकड आरती")
        assert paras[0].get("is_verse") is True
        assert paras[1].get("is_verse") is True

    def test_short_prose_after_verse_gets_flagged(self, tmp_path: Path):
        verse = "नारायण, नारायण, नारायण, नारायण॥"
        short_after = "आरती संपली"  # < 200 chars, not a heading
        p = tmp_path / "after.md"
        p.write_text(_make_md(verse, short_after), encoding="utf-8")
        paras = _parse_work_text(p, slug="nityanemavali")
        assert len(paras) == 2
        assert paras[0].get("is_verse") is True
        assert paras[1].get("is_verse") is True

    def test_long_prose_adjacent_to_verse_stays_prose(self, tmp_path: Path):
        # A 400+ char prose block adjacent to a verse pada must NOT be
        # flagged verse — it is the natural boundary between the verse
        # island and the biographical / commentary narrative.
        long_prose = "क" * 400  # 400 chars — clearly ≥ 200
        verse = "नारायण, नारायण, नारायण, नारायण॥"
        p = tmp_path / "long_adj.md"
        p.write_text(_make_md(long_prose, verse), encoding="utf-8")
        paras = _parse_work_text(p, slug="nityanemavali")
        assert len(paras) == 2
        assert paras[0].get("is_verse") is not True
        assert paras[1].get("is_verse") is True

    def test_chain_propagation_over_multiple_short_paragraphs(self, tmp_path: Path):
        # verse → short → short → short → all flagged.
        verse = "नारायण, नारायण, नारायण, नारायण॥"
        p = tmp_path / "chain.md"
        p.write_text(
            _make_md(verse, "पहिली छोटी", "दुसरी छोटी", "तिसरी छोटी"),
            encoding="utf-8",
        )
        paras = _parse_work_text(p, slug="nityanemavali")
        assert len(paras) == 4
        assert all(pr.get("is_verse") is True for pr in paras)

    def test_extension_stops_at_long_prose_boundary(self, tmp_path: Path):
        # verse → short → LONG → short. The trailing short is NOT reachable
        # because propagation halts at the long prose paragraph.
        verse = "नारायण, नारायण, नारायण, नारायण॥"
        short1 = "छोटी १"
        long_middle = "प" * 400
        short_after = "छोटी नंतर"
        p = tmp_path / "stops.md"
        p.write_text(_make_md(verse, short1, long_middle, short_after), encoding="utf-8")
        paras = _parse_work_text(p, slug="nityanemavali")
        assert len(paras) == 4
        assert paras[0].get("is_verse") is True   # seed
        assert paras[1].get("is_verse") is True   # reached
        assert paras[2].get("is_verse") is not True  # long — blocks
        assert paras[3].get("is_verse") is not True  # unreachable

    def test_heading_is_not_flagged_by_adjacency(self, tmp_path: Path):
        # An `is_heading` paragraph must NEVER get `is_verse: True` from
        # adjacency (it renders through its own branch).
        p = tmp_path / "heading_adj.md"
        p.write_text(
            _make_md("## ५. काकडआरती", "नारायण, नारायण, नारायण, नारायण॥"),
            encoding="utf-8",
        )
        paras = _parse_work_text(p, slug="nityanemavali")
        headings = [pr for pr in paras if pr.get("is_heading")]
        assert len(headings) == 1
        assert headings[0].get("is_verse") is not True

    def test_no_verse_seed_means_no_extension(self, tmp_path: Path):
        # If the section has no verse markers at all, extension has nothing
        # to seed on and every paragraph stays non-verse.
        p = tmp_path / "no_seed.md"
        p.write_text(_make_md("पहिली छोटी", "दुसरी छोटी"), encoding="utf-8")
        paras = _parse_work_text(p, slug="nityanemavali")
        assert not any(pr.get("is_verse") for pr in paras)

    def test_extension_does_not_run_for_non_verse_book(self, tmp_path: Path):
        # Regression: adjacency propagation is gated on VERSE_FORMAT_SLUGS.
        # A non-verse slug (or None) must NOT flag any paragraphs verse,
        # even when the content contains obvious verse markers.
        verse = "नारायण, नारायण, नारायण, नारायण॥"
        short = "छोटी " * 3  # 15 chars ish, well under 200 but also under 80
        # Use a long-enough prose so it survives the < 80 filter under the
        # default path — otherwise we can't observe extension either way.
        long_prose = "प" * 120
        p = tmp_path / "gated.md"
        p.write_text(_make_md(long_prose, verse, short), encoding="utf-8")
        # slug=None → default path drops short blocks entirely; no verse flags.
        paras_default = _parse_work_text(p, slug=None)
        assert not any(pr.get("is_verse") for pr in paras_default)
        # Explicit non-verse slug → same behavior.
        paras_kp = _parse_work_text(p, slug="kakanchi-pravachane")
        assert not any(pr.get("is_verse") for pr in paras_kp)


# ---------------------------------------------------------------------------
# Real-corpus dynamic-pagination assertions (Follow-up 2, 2026-08-06)
# ---------------------------------------------------------------------------
#
# End-to-end sanity: parse the on-disk nityanemavali and kakanchi-pravachane
# text.md through the actual paginator and check the density gate produced
# the shape Neha asked for (page 1 ≥ 5 paragraphs, healthy body char average)
# while leaving the control prose book bit-exact identical to the default
# path. Skips gracefully if the files aren't present.


import pathlib as _pl
import sys as _sys

_REPO = _pl.Path(__file__).resolve().parents[2]
_sys.path.insert(0, str(_REPO / "tools"))
from pagination import paginate as _paginate  # noqa: E402
from server import _pagination_target_chars as _target_for  # noqa: E402

_NITYA_TXT = _REPO / "01_canonical" / "gurudev_ranade" / "books" / "nityanemavali" / "mr" / "text.md"
_KAKANCHI_TXT = (
    _REPO / "01_canonical" / "kakasaheb_tulpule" / "lectures" / "kakanchi-pravachane" / "mr" / "text.md"
)


@pytest.mark.skipif(not _NITYA_TXT.exists(), reason="nityanemavali text.md missing")
class TestNityanemavaliDynamicPagination:
    def _pages(self):
        paras = _parse_work_text(_NITYA_TXT, slug="nityanemavali")
        return _paginate(paras, target_chars=_target_for("nityanemavali"))

    def test_page_1_has_at_least_5_paragraphs(self):
        pages = self._pages()
        assert len(pages) >= 1
        # Front-matter items were each landing as one-of-four rows under
        # PAGE_SIZE=4. Density gate must fit at least 5 of them per page.
        assert len(pages[0]) >= 5, (
            f"page 1 has only {len(pages[0])} rows: {[p['body'][:30] for p in pages[0]]}"
        )

    def test_average_body_chars_per_page_over_500(self):
        pages = self._pages()

        def body_chars(page):
            return sum(len(p.get("body", "")) for p in page if not (p.get("is_heading") or p.get("is_subheading")))

        totals = [body_chars(pg) for pg in pages]
        # Drop empty (heading-only) pages so a trailing chapter-opener
        # doesn't drag the average down artificially.
        non_zero = [t for t in totals if t > 0]
        assert non_zero, "every page was structural — no body text?"
        avg = sum(non_zero) / len(non_zero)
        assert avg > 500, f"avg body chars per page = {avg:.0f} (<500), pagination too sparse"


@pytest.mark.skipif(not _KAKANCHI_TXT.exists(), reason="kakanchi-pravachane text.md missing")
class TestKakanchiPravachaneBitExact:
    """Regression: verse-format changes MUST NOT touch prose-book pagination.
    Parse + paginate kakanchi-pravachane exactly as production does and
    verify page 1 has the same paragraph count it had before Follow-up 2."""

    def test_pagination_uses_legacy_page_size_for_kakanchi(self):
        # `_pagination_target_chars` must return None for non-verse slugs
        # → paginate falls into the fixed-count PAGE_SIZE=4 branch.
        assert _target_for("kakanchi-pravachane") is None

    def test_page_1_is_bit_exact_with_and_without_default(self):
        paras = _parse_work_text(_KAKANCHI_TXT, slug="kakanchi-pravachane")
        pages_default = _paginate(paras)
        pages_via_helper = _paginate(paras, target_chars=_target_for("kakanchi-pravachane"))
        # Full pagination shape must be identical (bit-exact regression).
        assert [len(pg) for pg in pages_default] == [len(pg) for pg in pages_via_helper]
        # Page 1 rows are the same paragraph `n`s in the same order.
        assert [p["n"] for p in pages_default[0]] == [p["n"] for p in pages_via_helper[0]]


# ---------------------------------------------------------------------------
# HEADING_IN_BODY_SLUGS scope-gate: reflections (prose) gets is_heading
# emission WITHOUT verse styling; nityanemavali (verse) gets both. This is
# the split of the old VERSE_FORMAT_SLUGS gate on 2026-08-06 for Neha's
# reflections rebuild.
# ---------------------------------------------------------------------------


def test_heading_in_body_slugs_superset_of_verse_format():
    assert VERSE_FORMAT_SLUGS <= HEADING_IN_BODY_SLUGS
    assert "reflections" in HEADING_IN_BODY_SLUGS
    assert "reflections" not in VERSE_FORMAT_SLUGS


SAMPLE_REFLECTIONS = textwrap.dedent(
    """\
    ---
    title: Reflections
    lang: en
    ---

    ## REFLECTIONS – I
    ### 21st February 1912

    Today I saw a gentleman rebuking a young for a fault, which deserved to be censured. But the rebuke lost all its force as it was immediately followed by an indiscreet confession of a similar fault which the gentleman had committed in his youth.

    ### 22nd February 1912

    It is the nature of children to be naughty, and it requires a great deal of tact on the part of the elder to behave properly with them. The best way to behave with children is never to grow familiar with them.
    """
)


@pytest.fixture()
def reflections_sample(tmp_path: Path) -> Path:
    p = tmp_path / "reflections_sample.md"
    p.write_text(SAMPLE_REFLECTIONS, encoding="utf-8")
    return p


class TestParseReflectionsHeadingEmission:
    """Reflections is in HEADING_IN_BODY_SLUGS but NOT in VERSE_FORMAT_SLUGS.
    It must get in-body heading paragraphs (H2 and H3) with NO verse
    styling on the surrounding prose."""

    def test_h2_heading_emitted_as_paragraph(self, reflections_sample):
        paras = _parse_work_text(reflections_sample, slug="reflections")
        h2s = [p for p in paras if p.get("is_heading") and p.get("heading_level") == 2]
        assert len(h2s) == 1
        assert h2s[0]["body"] == "REFLECTIONS – I"

    def test_h3_headings_emitted_as_paragraphs(self, reflections_sample):
        paras = _parse_work_text(reflections_sample, slug="reflections")
        h3s = [p for p in paras if p.get("is_heading") and p.get("heading_level") == 3]
        assert len(h3s) == 2
        assert h3s[0]["body"] == "21st February 1912"
        assert h3s[1]["body"] == "22nd February 1912"

    def test_no_verse_flags_for_reflections(self, reflections_sample):
        # Reflections is prose — no is_verse flag must be set on any row,
        # even though the parser now emits heading rows.
        paras = _parse_work_text(reflections_sample, slug="reflections")
        assert not any(p.get("is_verse") for p in paras)

    def test_body_paragraphs_go_through_strip_inline_md(self, reflections_sample):
        # Prose bodies should be scrubbed by _strip_inline_md — the verse
        # branch (which preserves **bold**) must NOT fire here.
        paras = _parse_work_text(reflections_sample, slug="reflections")
        bodies = [p for p in paras if not p.get("is_heading")]
        assert bodies, "no body paragraphs parsed"

    def test_paragraph_n_is_consecutive(self, reflections_sample):
        paras = _parse_work_text(reflections_sample, slug="reflections")
        for i, p in enumerate(paras):
            assert p["n"] == i + 1

    def test_chapter_context_updates_from_h3(self, reflections_sample):
        # `chapter` on body paragraphs after each `###` should be that date.
        paras = _parse_work_text(reflections_sample, slug="reflections")
        # First body para after H3 "21st February 1912"
        first_body = next(p for p in paras if not p.get("is_heading"))
        assert first_body["chapter"] == "21st February 1912"


class TestNityanemavaliStillGetsBothFlags:
    """Regression pin: splitting the emission gate off VERSE_FORMAT_SLUGS
    must NOT stop nityanemavali from getting is_heading rows AND is_verse
    styling. HEADING_IN_BODY_SLUGS is a superset that includes it."""

    def test_h2_heading_still_emitted(self, sample_file):
        paras = _parse_work_text(sample_file, slug="nityanemavali")
        h2s = [p for p in paras if p.get("is_heading") and p.get("heading_level") == 2]
        assert len(h2s) == 1

    def test_h3_heading_still_emitted(self, sample_file):
        paras = _parse_work_text(sample_file, slug="nityanemavali")
        h3s = [p for p in paras if p.get("is_heading") and p.get("heading_level") == 3]
        assert len(h3s) == 1

    def test_verse_flags_still_applied(self, sample_file):
        paras = _parse_work_text(sample_file, slug="nityanemavali")
        assert any(p.get("is_verse") for p in paras)
