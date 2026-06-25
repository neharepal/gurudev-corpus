"""Tests for the character-junk garble verifier (clean_quote_body)."""

import schemas

ZWSP = chr(0x200B)   # zero-width space (junk)
BOM = chr(0xFEFF)    # byte-order mark (junk)
ZWJ = chr(0x200D)    # zero-width joiner (meaningful in Devanagari -> keep)
FFFD = chr(0xFFFD)   # Unicode replacement char (lost glyph -> space)
NUL = chr(0x00)
TAB = chr(0x09)
LF = chr(0x0A)
CR = chr(0x0D)


def test_strips_control_zerowidth_bom():
    s = "a" + NUL + "b" + ZWSP + "c" + BOM + "d"
    assert schemas.clean_quote_body(s) == "abcd"


def test_replacement_char_becomes_space():
    s = "partake of" + FFFD + "amirasa"
    assert schemas.clean_quote_body(s) == "partake of amirasa"


def test_keeps_devanagari_and_zwj():
    deva = "बाबांच्या आठवणी"
    assert schemas.clean_quote_body(deva) == deva
    with_zwj = "क" + ZWJ + "ष"
    assert schemas.clean_quote_body(with_zwj) == with_zwj


def test_keeps_tab_newline_cr():
    s = "line1" + LF + "line2" + TAB + "end" + CR + "x"
    assert schemas.clean_quote_body(s) == s


def test_clean_text_unchanged():
    s = "I believe that Bhakti does not consist in mere observance."
    assert schemas.clean_quote_body(s) == s
    assert schemas.clean_quote_body("") == ""


def test_splice_cleans_the_body():
    chunk = {
        "meta": {"title": "W", "author": "a", "kind": "canonical"},
        "text": "Surrender" + ZWSP + " yourself" + FFFD + " to God fully.",
    }
    q = {
        "passage": "A",
        "quoteStart": "Surrender yourself",
        "quoteEnd": "to God fully.",
        "location": "",
    }
    schemas.splice_quote_dict(q, {"A": chunk})
    body = q["body"]
    assert ZWSP not in body and FFFD not in body
    assert "Surrender yourself" in body
    assert "to God fully" in body
