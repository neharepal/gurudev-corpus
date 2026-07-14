"""Split one arthasahit entry into (verse, meaning). The verse is Gurudev's
selection (citable); the meaning is sadhak-authored (retrieval-only). Boundary
markers vary per book; return meaning=None when no confident split exists so the
caller can mark the child retrieval-only rather than mis-cite the meaning. (RFC-017.)"""
from __future__ import annotations
import re

# Strongest boundary: a line that begins the meaning with 'अर्थ' (± number/dash).
_ARTHA_RE = re.compile(r"(?m)^\s*अर्थ\b.*")
# Next: an English gloss in parentheses (the trilingual editions' translation).
_ENGLISH_GLOSS_RE = re.compile(r"\([^)]*[A-Za-z][^)]*\)")


def split_verse_meaning(entry: str) -> tuple[str, str | None]:
    e = (entry or "").strip()
    if not e:
        return "", None
    m = _ARTHA_RE.search(e)
    if m and m.start() > 0:
        return e[:m.start()].strip(), e[m.start():].strip()
    g = _ENGLISH_GLOSS_RE.search(e)
    if g and g.start() > 0:
        return e[:g.start()].strip(), e[g.start():].strip()
    return e, None
