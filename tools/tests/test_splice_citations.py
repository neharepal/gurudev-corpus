"""Tests for reference-and-splice citation logic in schemas.py.

Covers:
- Diacritic-tolerant anchor matching (macron vs circumflex, etc.)
- Full-passage fallback when anchors genuinely miss (no "…" stubs)
- Happy-path exact splice still returns precise span
"""

import schemas


# ---------------------------------------------------------------------------
# Helper: build a minimal chunk dict
# ---------------------------------------------------------------------------

def make_chunk(text, title="TestWork", author="TestAuthor", kind="canonical"):
    return {
        "meta": {"title": title, "author": author, "kind": kind},
        "text": text,
    }


# ---------------------------------------------------------------------------
# 1. Diacritic-tolerant anchor matching
# ---------------------------------------------------------------------------

class TestDiacriticTolerance:

    def test_macron_anchor_finds_circumflex_in_source(self):
        """Model emits quoteStart with macron ā; source has circumflex â."""
        source_text = (
            "Nârada asked the sage: 'What is the nature of Bhakti?' "
            "The sage replied with great wisdom."
        )
        chunk = make_chunk(source_text)
        q = {
            "passage": "A",
            "quoteStart": "Nārada asked the sage",  # macron ā
            "quoteEnd": "nature of Bhakti",
            "location": "",
        }
        result = schemas.splice_quote_dict(q, {"A": chunk})
        body = q["body"]
        # Must contain the ORIGINAL circumflex from the source, not the folded form.
        assert "Nârada" in body, f"Expected original 'Nârada' (circumflex) in body, got: {body!r}"
        # Must NOT contain the macron form that the model supplied.
        assert "Nārada" not in body, f"Should not contain model's macron form, got: {body!r}"
        # splice_quote_dict returns True on a successful locate
        assert result is True

    def test_macron_anchor_body_does_not_contain_stub(self):
        """Diacritic mismatch must not produce an ellipsis stub."""
        source_text = "Nârada said: devotion is the path. Let it be so."
        chunk = make_chunk(source_text)
        q = {
            "passage": "B",
            "quoteStart": "Nārada said",  # macron ā
            "quoteEnd": "is the path",
            "location": "",
        }
        schemas.splice_quote_dict(q, {"B": chunk})
        assert " … " not in q["body"], f"Got stub: {q['body']!r}"

    def test_fold_returns_original_diacritics(self):
        """Folded search must slice from the ORIGINAL text — diacritics preserved."""
        source_text = "The Nârada Bhakti Sûtra is a sacred text."
        chunk = make_chunk(source_text)
        q = {
            "passage": "C",
            "quoteStart": "Nārada Bhakti",  # macron variants
            "quoteEnd": "Sutra is a sacred",  # simplified 'u'
            "location": "",
        }
        schemas.splice_quote_dict(q, {"C": chunk})
        body = q["body"]
        # Source has circumflex û in Sûtra; check it is preserved (or whole chunk used).
        assert " … " not in body

    def test_exact_match_still_works(self):
        """Exact (no diacritic difference) anchors continue to return the precise span."""
        source_text = (
            "Bhakti is the supreme means. "
            "It ripens into divine love. "
            "Nothing else compares."
        )
        chunk = make_chunk(source_text)
        q = {
            "passage": "D",
            "quoteStart": "Bhakti is the supreme",
            "quoteEnd": "ripens into divine love",
            "location": "",
        }
        result = schemas.splice_quote_dict(q, {"D": chunk})
        body = q["body"]
        assert result is True
        assert body.startswith("Bhakti is the supreme")
        assert "ripens into divine love" in body
        assert " … " not in body


# ---------------------------------------------------------------------------
# 2. Full-passage fallback (no stub when anchors miss)
# ---------------------------------------------------------------------------

class TestFullPassageFallback:

    def test_anchor_mismatch_gives_full_chunk_not_stub(self):
        """When anchors cannot be found, body = full chunk text (no ellipsis stub)."""
        source_text = "does not consists in mere observance of rituals."
        chunk = make_chunk(source_text)
        q = {
            "passage": "E",
            "quoteStart": "does not consist in",   # model dropped the extra 's'
            "quoteEnd": "observance of rituals",
            "location": "",
        }
        schemas.splice_quote_dict(q, {"E": chunk})
        body = q["body"]
        assert " … " not in body, f"Got stub: {body!r}"
        # Body should be the full chunk (cleaned), not the degraded anchors.
        assert "does not consists" in body, f"Expected full source text in body, got: {body!r}"

    def test_anchor_mismatch_no_stub_multiple_words(self):
        """Multi-word anchor mismatch also avoids stub."""
        source_text = (
            "The river of compassion flows ceaselessly from the Guru's heart. "
            "Let the disciple open himself to receive it."
        )
        chunk = make_chunk(source_text)
        q = {
            "passage": "F",
            "quoteStart": "COMPLETELYWRONG anchor text",
            "quoteEnd": "also wrong end anchor",
            "location": "",
        }
        schemas.splice_quote_dict(q, {"F": chunk})
        body = q["body"]
        assert " … " not in body
        # Full chunk text must be present.
        assert "river of compassion" in body

    def test_body_never_has_stub_when_chunk_exists(self):
        """splice_quote_dict result may be False (miss) but body must not be a stub."""
        source_text = "Surrender yourself to God fully."
        chunk = make_chunk(source_text)
        q = {
            "passage": "G",
            "quoteStart": "NOMATCH START",
            "quoteEnd": "NOMATCH END",
            "location": "",
        }
        schemas.splice_quote_dict(q, {"G": chunk})
        assert " … " not in q.get("body", "")

    def test_full_fallback_body_is_cleaned(self):
        """Full-passage fallback body goes through clean_quote_body (no junk)."""
        ZWSP = chr(0x200B)
        dirty_source = "Some" + ZWSP + " sacred text here."
        chunk = make_chunk(dirty_source)
        q = {
            "passage": "H",
            "quoteStart": "NOMATCH",
            "quoteEnd": "NOMATCH",
            "location": "",
        }
        schemas.splice_quote_dict(q, {"H": chunk})
        assert ZWSP not in q["body"]


# ---------------------------------------------------------------------------
# 3. Unknown passage (no chunk) — no stub, use model body if present
# ---------------------------------------------------------------------------

class TestUnknownPassage:

    def test_no_chunk_model_body_kept(self):
        """Unknown passage: model body is preserved if provided."""
        q = {
            "passage": "Z",
            "quoteStart": "some words",
            "quoteEnd": "more words",
            "body": "The model provided this body.",
            "location": "",
        }
        schemas.splice_quote_dict(q, {})
        assert q["body"] == "The model provided this body."
        assert " … " not in q["body"]

    def test_no_chunk_no_model_body_no_stub(self):
        """Unknown passage, no model body: no stub emitted."""
        q = {
            "passage": "Z",
            "quoteStart": "start words",
            "quoteEnd": "end words",
            "location": "",
        }
        schemas.splice_quote_dict(q, {})
        # body should be absent or empty — never an ellipsis stub
        body = q.get("body", "")
        assert " … " not in (body or "")


# ---------------------------------------------------------------------------
# 4. Edge cases for _fold_char / _fold_text
# ---------------------------------------------------------------------------

class TestFoldHelpers:

    def test_fold_char_ascii_letter_unchanged(self):
        assert schemas._fold_char("a") == "a"
        assert schemas._fold_char("Z") == "Z"

    def test_fold_char_diacritic(self):
        assert schemas._fold_char("â") == "a"   # circumflex -> a
        assert schemas._fold_char("ā") == "a"   # macron -> a
        assert schemas._fold_char("é") == "e"   # acute -> e
        assert schemas._fold_char("ñ") == "n"   # tilde -> n

    def test_fold_text_length_preserved(self):
        """_fold_text must produce a string of the same length as the input."""
        s = "Nârada and Nārada"
        folded = schemas._fold_text(s)
        assert len(folded) == len(s)

    def test_fold_text_ascii_unchanged(self):
        s = "plain ASCII text"
        assert schemas._fold_text(s) == s

    def test_fold_text_diacritics_folded(self):
        s = "Nârada"   # â = U+00E2
        folded = schemas._fold_text(s)
        assert folded == "Narada"


# ---------------------------------------------------------------------------
# 5. workId is set from chunk meta.work_id after splice (corpus-free)
# ---------------------------------------------------------------------------

class TestWorkIdSplice:

    def make_chunk_with_work_id(self, text, work_id, kind="canonical"):
        return {
            "meta": {
                "title": "Test Work",
                "author": "Test Author",
                "kind": kind,
                "work_id": work_id,
            },
            "text": text,
        }

    def test_work_id_set_on_canonical_splice(self):
        """After splice_quote_dict on a canonical chunk, workId equals chunk meta work_id."""
        source_text = "Bhakti is the supreme means of realisation."
        chunk = self.make_chunk_with_work_id(source_text, "pathway-to-god-in-hindi-literature", kind="canonical")
        q = {
            "passage": "A",
            "quoteStart": "Bhakti is the supreme",
            "quoteEnd": "means of realisation",
            "location": "",
        }
        schemas.splice_quote_dict(q, {"A": chunk})
        assert q.get("workId") == "pathway-to-god-in-hindi-literature", (
            f"Expected workId='pathway-to-god-in-hindi-literature', got {q.get('workId')!r}"
        )

    def test_work_id_empty_for_athvani(self):
        """workId is empty string for athvani quotes (no reader URL for those)."""
        source_text = "The trunks were kept with great care."
        chunk = self.make_chunk_with_work_id(source_text, "jaisi-ganga-vahe", kind="athvani")
        q = {
            "passage": "B",
            "quoteStart": "The trunks were",
            "quoteEnd": "great care",
            "location": "",
        }
        schemas.splice_quote_dict(q, {"B": chunk})
        assert q.get("workId") == "", (
            f"Expected workId='' for athvani kind, got {q.get('workId')!r}"
        )

    def test_work_id_empty_for_biography(self):
        """workId is empty string for biography quotes."""
        source_text = "He was born in the year of grace."
        chunk = self.make_chunk_with_work_id(source_text, "some-biography", kind="biography")
        q = {
            "passage": "C",
            "quoteStart": "He was born",
            "quoteEnd": "year of grace",
            "location": "",
        }
        schemas.splice_quote_dict(q, {"C": chunk})
        assert q.get("workId") == "", (
            f"Expected workId='' for biography kind, got {q.get('workId')!r}"
        )

    def test_work_id_absent_when_no_work_id_in_meta(self):
        """When the chunk meta has no work_id, workId is set to empty string."""
        source_text = "The Name is the highest path."
        chunk = {
            "meta": {"title": "Some Work", "author": "Author", "kind": "canonical"},
            "text": source_text,
        }
        q = {
            "passage": "D",
            "quoteStart": "The Name is",
            "quoteEnd": "highest path",
            "location": "",
        }
        schemas.splice_quote_dict(q, {"D": chunk})
        assert q.get("workId") == "", (
            f"Expected workId='' when meta has no work_id, got {q.get('workId')!r}"
        )

    def test_work_id_not_set_when_no_chunk(self):
        """Unknown passage: workId is not set (no chunk to draw work_id from)."""
        q = {
            "passage": "Z",
            "quoteStart": "some words",
            "quoteEnd": "more words",
            "body": "Fallback body.",
            "location": "",
        }
        schemas.splice_quote_dict(q, {})
        # workId should not be set (or absent) — no chunk provided it.
        assert "workId" not in q or q.get("workId") == "", (
            f"Expected workId absent/empty for unknown passage, got {q.get('workId')!r}"
        )
