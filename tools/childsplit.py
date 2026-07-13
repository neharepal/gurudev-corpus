"""Split a parent section into child units (sentence / verse) for small-to-big
retrieval (RFC-017). embed_text carries a neighbor window so short children still
embed with signal; text is the citable/raw unit."""
from __future__ import annotations
import re

SENTENCE_END_RE = re.compile(r"(?<=[.!?।॥])\s+")
DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]")
_VERSE_BOUNDARY_RE = re.compile(r"(?<=[।॥])\s*")


def _is_verse(text: str) -> bool:
    # Verse if Devanagari-heavy AND uses danda punctuation.
    deva = len(DEVANAGARI_RE.findall(text))
    return deva / max(len(text), 1) > 0.3 and ("।" in text or "॥" in text)


def split_into_children(section_text: str, *, window: int = 1) -> list[dict]:
    text = (section_text or "").strip()
    if not text:
        return []
    if _is_verse(text):
        parts = [p.strip() for p in _VERSE_BOUNDARY_RE.split(text) if p.strip()]
    else:
        parts = [p.strip() for p in SENTENCE_END_RE.split(text) if p.strip()]
    if not parts:
        parts = [text]
    out = []
    for i, p in enumerate(parts):
        lo = max(0, i - window)
        hi = min(len(parts), i + window + 1)
        embed = " ".join(parts[lo:hi]) if window > 0 else p
        out.append({"text": p, "embed_text": embed})
    return out
