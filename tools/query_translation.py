"""Cross-lingual query expansion for retrieval.

The corpus is ~85% Devanagari (Marathi/Hindi). bge-m3 matches cross-lingually,
but same-language cosines are systematically higher than cross-language ones,
so an English (or romanized) query lets English works crowd the relevant
Devanagari works below the top-k cutoff.

Fix: render a non-Devanagari query into Marathi (Devanagari), embed BOTH, and
let dense retrieval take the per-passage MAX. A Devanagari passage then competes
at its monolingual-strength score instead of its depressed cross-lingual one.

Mirrors intent.py: a heuristic decides when translation is even needed; a cached
Haiku call does the work; any failure returns None so retrieval falls back to
English-only (never blocks).
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Callable, Optional

_DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]")
_TRANSLATE_MODEL = "claude-haiku-4-5"  # cheapest model; translating a short query
_client = None


def needs_translation(query: str) -> bool:
    """True when the query has no Devanagari, so a Marathi rendering would help.

    A query that already contains Devanagari matches the corpus in-script, so
    translating it adds nothing (and would risk drift on mixed-script queries).
    """
    return bool(query) and _DEVANAGARI_RE.search(query) is None


def translate_query(
    query: str,
    *,
    use_llm: bool = True,
    translator: Optional[Callable[[str], Optional[str]]] = None,
) -> Optional[str]:
    """Return a Marathi (Devanagari) rendering of `query`, or None.

    None means "don't add a second vector": the query is empty, already has
    Devanagari, translation is disabled, or the call failed / produced no
    Devanagari. Never raises — retrieval must not depend on this.
    """
    if not needs_translation(query):
        return None
    if not use_llm:
        return None
    fn = translator or _default_translate
    try:
        out = fn(query)
    except Exception:
        return None
    if out and _DEVANAGARI_RE.search(out):
        return out.strip()
    return None


def _get_client():
    global _client
    if _client is None:
        from anthropic import Anthropic  # lazy import keeps unit tests SDK-free
        _client = Anthropic()
    return _client


@lru_cache(maxsize=512)
def _default_translate(query: str) -> Optional[str]:
    """Translate a query to Marathi with Haiku. Cached per query. None on failure."""
    prompt = (
        "You translate SEARCH QUERIES into Marathi (Devanagari script) for a "
        "Marathi/Hindi spiritual corpus about Gurudev R. D. Ranade and the Nimbargi "
        "(Inchgeri) lineage.\n"
        "Rules:\n"
        "- Output ONLY the Marathi translation — no quotes, transliteration, or notes.\n"
        "- Render romanized Marathi/Sanskrit terms in Devanagari "
        "(e.g. 'Charitra' -> चरित्र, 'Tatvajnan' -> तत्त्वज्ञान, 'athvani' -> आठवणी, "
        "'sadhana' -> साधना).\n"
        "- Keep the meaning of the search intent; do not answer the question.\n\n"
        f"Query: {query}\nMarathi:"
    )
    resp = _get_client().messages.create(
        model=_TRANSLATE_MODEL,
        max_tokens=128,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(
        b.text for b in resp.content if getattr(b, "type", None) == "text"
    ).strip()
    return text or None
