"""Deterministic per-chunk quality scoring to downweight OCR/structural junk.

The corpus is TRILINGUAL (Marathi/Hindi/English). So "real prose" is detected
by LETTER density (Devanagari OR Latin both count) plus stopword presence in
either language — NOT by Devanagari ratio, which would wrongly flag the ~60%
English canonical works. Junk = short structural fragments (headings, page
markers, bare titles), digit/list pages (page numbers, census/village lists),
and symbol garble (bad OCR). Pure functions; no I/O.
"""
from __future__ import annotations
import re

_DEVA = re.compile(r"[ऀ-ॿ]")
_LATIN = re.compile(r"[A-Za-z]")

# Bilingual stopwords — the highest-signal "coherent prose vs list/heading" check.
_EN_STOP = frozenset({
    "the", "and", "of", "to", "in", "a", "is", "that", "for", "it", "as",
    "with", "was", "his", "he", "on", "are", "this", "which", "by", "not",
})
_MR_STOP = frozenset({
    "आणि", "आहे", "या", "तो", "हे", "मध्ये", "पण", "व", "की", "नाही",
    "होते", "त्या", "हा", "ही", "तें", "त्यांनी", "असे", "होता",
})
_STOP = _EN_STOP | _MR_STOP


def _ratios(text: str) -> tuple[float, float, float]:
    """Return (letter_ratio, digit_ratio, symbol_ratio) over non-space chars."""
    non_space = [c for c in text if not c.isspace()]
    if not non_space:
        return 0.0, 0.0, 1.0
    n = len(non_space)
    letters = sum(1 for c in non_space if (_DEVA.match(c) or _LATIN.match(c)) and not c.isdigit())
    digits = sum(1 for c in non_space if c.isdigit())
    symbols = n - letters - digits
    return letters / n, digits / n, symbols / n


def _stopword_count(text: str) -> int:
    toks = [t.strip(".,;:!?\"'()[]{}…।॥") for t in text.lower().split()]
    return sum(1 for t in toks if t in _STOP)


def quality_score(text: str) -> float:
    """Return a [0,1] prose-quality score (1.0 = clean prose, low = junk).

    Multiplicative soft penalties so any single strong junk signal pulls the
    score down. Thresholds are conservative to avoid false-positives on real
    (esp. short-but-legit) content; tune on labeled chunks if needed.
    """
    s = text.strip()
    if not s:
        return 0.0
    letter_r, digit_r, symbol_r = _ratios(s)
    stop_n = _stopword_count(s)
    length = len(s)

    score = 1.0
    # Length: short fragments (headings, markers, bare titles) are almost always junk.
    if length < 100:
        score *= 0.15
    elif length < 200:
        score *= 0.6
    # Letters must dominate real prose.
    if letter_r < 0.45:
        score *= 0.2
    elif letter_r < 0.6:
        score *= 0.6
    # Digit-heavy = page numbers / lists / census tables.
    if digit_r > 0.25:
        score *= 0.2
    elif digit_r > 0.15:
        score *= 0.6
    # Symbol-heavy = OCR garble.
    if symbol_r > 0.25:
        score *= 0.4
    # Coherent prose has stopwords; lists/headings/garble do not.
    if length >= 200 and stop_n < 2:
        score *= 0.3
    return round(max(0.0, min(1.0, score)), 4)


def is_junk(text: str, threshold: float = 0.5) -> bool:
    """True when quality_score is below `threshold` (default 0.5)."""
    return quality_score(text) < threshold
