"""Cross-lingual query expansion for retrieval.

The corpus is ~85% Devanagari (Marathi/Hindi). bge-m3 matches cross-lingually,
but same-language cosines are systematically higher than cross-language ones,
so an English (or romanized) query lets English works crowd the relevant
Devanagari works below the top-k cutoff, and vice-versa for Marathi queries
against English-language canonical works.

Fix (bidirectional):
  EN/romanized query → Marathi (Devanagari) translation → second vector.
  Devanagari query   → English translation              → second vector.
In both cases retrieval takes the per-passage MAX so the corpus's own-language
passages compete at their monolingual-strength cosine.

Mirrors intent.py: a heuristic decides when translation is needed; a cached
Haiku call does the work; any failure returns None so retrieval falls back to
the single-vector path (never blocks).
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

    A query that already contains Devanagari matches the Devanagari corpus
    in-script; it benefits instead from `needs_reverse_translation`.
    """
    return bool(query) and _DEVANAGARI_RE.search(query) is None


def needs_reverse_translation(query: str) -> bool:
    """True when the query HAS Devanagari, so an English rendering would help.

    English-language canonical works (Gurudev's own scholarly writings are
    ~60% English) embed far from a Devanagari query even when the semantic
    content is identical.  Adding an English translation vector lets those
    works compete at their monolingual-strength cosine.
    Mixed-script queries qualify: the Devanagari content triggers the reverse
    path so the English portion of the corpus is not systematically depressed.
    """
    return bool(query) and _DEVANAGARI_RE.search(query) is not None


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


def translate_to_english(
    query: str,
    *,
    use_llm: bool = True,
    translator: Optional[Callable[[str], Optional[str]]] = None,
) -> Optional[str]:
    """Return an English rendering of a Devanagari (Marathi) `query`, or None.

    This is the reverse direction of `translate_query`: a Marathi query is
    translated into English so that English-language canonical works can
    compete at their monolingual-strength cosine score.

    None means "don't add a reverse vector": the query has no Devanagari,
    translation is disabled (use_llm=False), or the call failed.  Never
    raises — retrieval must not depend on this.

    Limitation: the implementation uses the same Haiku LLM as the forward
    direction (EN→MR).  When use_llm=False (e.g. the offline eval harness),
    this always returns None; the eval then measures only bge-m3's native
    cross-lingual matching, which is the pre-fix baseline.
    """
    if not needs_reverse_translation(query):
        return None
    if not use_llm:
        return None
    fn = translator or _default_translate_to_english
    try:
        out = fn(query)
    except Exception:
        return None
    # Verify the output is non-empty and contains no Devanagari (we want English)
    if out and not _DEVANAGARI_RE.search(out):
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


@lru_cache(maxsize=512)
def _default_translate_to_english(query: str) -> Optional[str]:
    """Translate a Devanagari query to English with Haiku. Cached per query. None on failure."""
    prompt = (
        "You translate SEARCH QUERIES from Marathi/Hindi (Devanagari script) into "
        "English for a spiritual corpus about Gurudev R. D. Ranade and the Nimbargi "
        "(Inchgeri) lineage.\n"
        "Rules:\n"
        "- Output ONLY the English translation — no Devanagari, no transliteration notes.\n"
        "- Render Marathi/Sanskrit spiritual terms in standard English equivalents "
        "(e.g. साधना -> sadhana, भक्ती -> bhakti, आठवणी -> recollections, "
        "तत्त्वज्ञान -> philosophy, समाधी -> samadhi).\n"
        "- Keep the meaning of the search intent; do not answer the question.\n\n"
        f"Query: {query}\nEnglish:"
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
