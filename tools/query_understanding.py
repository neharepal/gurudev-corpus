"""Query rewriting + HyDE for retrieval (mirrors query_translation.py).

A bare/short query lands in a sparse embedding region; a full-prose rewrite or
a hypothetical answer paragraph (HyDE) moves the search ANCHOR into the
descriptive-prose neighborhood where the answer actually lives — the effect we
already observe when a user asks a full question. Retrieval embeds these
ADDITIONAL query strings alongside the original (BM25 on the original stays the
exact-match backbone). Cached Haiku; any failure returns None (no-op).
"""
from __future__ import annotations
from functools import lru_cache
from typing import Callable, Optional

_MODEL = "claude-haiku-4-5"
_client = None


def _get_client():
    global _client
    if _client is None:
        from anthropic import Anthropic
        _client = Anthropic()
    return _client


def _clean(out: Optional[str], original: str) -> Optional[str]:
    if not out:
        return None
    out = out.strip()
    if not out or out == original.strip():
        return None
    return out


def rewrite_query(query, *, use_llm=True, rewriter: Optional[Callable[[str], Optional[str]]] = None):
    if not query or not query.strip():
        return None
    if rewriter is None and not use_llm:
        return None
    fn = rewriter or _default_rewrite
    try:
        return _clean(fn(query), query)
    except Exception:
        return None


def hypothetical_doc(query, *, use_llm=True, generator: Optional[Callable[[str], Optional[str]]] = None):
    if not query or not query.strip():
        return None
    if generator is None and not use_llm:
        return None
    fn = generator or _default_hyde
    try:
        return _clean(fn(query), query)
    except Exception:
        return None


@lru_cache(maxsize=512)
def _default_rewrite(query: str) -> Optional[str]:
    prompt = (
        "Rewrite this search query for a Marathi/Hindi/English corpus about "
        "Gurudev R. D. Ranade and the Nimbargi (Inchgeri) lineage into a fuller, "
        "explicit search query. Keep the SAME language/script. Expand a bare "
        "topic into what a reader would want to know (what it is, who/where/when, "
        "significance). Do NOT invent facts. Output ONLY the rewritten query.\n\n"
        f"Query: {query}\nRewritten:"
    )
    r = _get_client().messages.create(model=_MODEL, max_tokens=96,
                                      messages=[{"role": "user", "content": prompt}])
    return "".join(b.text for b in r.content if getattr(b, "type", None) == "text").strip() or None


@lru_cache(maxsize=512)
def _default_hyde(query: str) -> Optional[str]:
    prompt = (
        "Write a short hypothetical passage (2-4 sentences) that would answer "
        "this question about Gurudev R. D. Ranade / the Nimbargi (Inchgeri) "
        "lineage, in the SAME language/script as the question. It is a SEARCH "
        "AID, not a shown answer: stay general, do not fabricate specific names, "
        "dates, or numbers. Output ONLY the passage.\n\n"
        f"Question: {query}\nPassage:"
    )
    r = _get_client().messages.create(model=_MODEL, max_tokens=160,
                                      messages=[{"role": "user", "content": prompt}])
    return "".join(b.text for b in r.content if getattr(b, "type", None) == "text").strip() or None
