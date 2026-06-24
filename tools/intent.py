"""Query-intent classification for intent-aware citation ranking (RFC-011).

A multilingual heuristic classifies the common cases for free; an injectable
LLM fallback (wired in Task 3) handles ambiguous queries. Intent never blocks
retrieval — any failure resolves to "unknown".
"""

from __future__ import annotations

from functools import lru_cache
from typing import Callable, Optional

INTENTS = ("doctrinal", "narrative", "navigational", "unknown")

# Lowercased substring cues per intent (Devanagari has no case). Seed lists —
# expand against real queries (RFC-011 open question).
_CUES: dict[str, tuple[str, ...]] = {
    "doctrinal": (
        "teaching", "philosophy", "philosophical", "doctrine", "meaning",
        "concept", "principle", "what does", "explain",
        "शिकवण", "तत्त्वज्ञान", "अर्थ", "सिद्धांत", "तत्त्व",
    ),
    "narrative": (
        "athvani", "story", "stories", "incident", "anecdote", "memory",
        "memories", "recollection",
        "आठवण", "प्रसंग", "गोष्ट", "कथा",
    ),
    "navigational": (
        "which works", "which books", "what books", "list", "index",
        "catalogue", "catalog", "structure", "how many",
        "कोणते ग्रंथ", "यादी", "सूची",
    ),
}


def _heuristic_intent(query: str) -> Optional[str]:
    """Confident intent label, or None if no cues fire or two intents tie."""
    q = query.lower()
    hits = {name: sum(1 for cue in cues if cue in q) for name, cues in _CUES.items()}
    best = max(hits, key=hits.get)
    top = hits[best]
    if top == 0:
        return None  # no cues -> ambiguous
    if sum(1 for v in hits.values() if v == top) > 1:
        return None  # tie -> ambiguous
    return best


def classify_intent(
    query: str,
    *,
    use_llm_fallback: bool = True,
    llm_fallback: Optional[Callable[[str], Optional[str]]] = None,
) -> str:
    """Return one of INTENTS. Heuristic first; LLM fallback only when ambiguous."""
    label = _heuristic_intent(query)
    if label is not None:
        return label
    if use_llm_fallback:
        fb = llm_fallback or _default_llm_fallback
        try:
            guess = fb(query)
        except Exception:
            guess = None
        if guess in INTENTS and guess != "unknown":
            return guess
    return "unknown"


_INTENT_MODEL = "claude-haiku-4-5"  # cheapest model; intent is a 1-word task
_client = None


def _get_client():
    global _client
    if _client is None:
        from anthropic import Anthropic  # lazy import keeps unit tests SDK-free
        _client = Anthropic()
    return _client


@lru_cache(maxsize=512)
def _default_llm_fallback(query: str) -> Optional[str]:
    """Classify an ambiguous query with Haiku. Cached per query. None on failure."""
    prompt = (
        "Classify this question about a spiritual corpus into exactly one intent "
        "label. Reply with only the label word.\n"
        "- doctrinal: teaching, philosophy, meaning, or doctrine\n"
        "- narrative: a story, anecdote, incident, or recollection (athvani)\n"
        "- navigational: which works/books exist, lists, structure, counts\n\n"
        f"Question: {query}\nLabel:"
    )
    resp = _get_client().messages.create(
        model=_INTENT_MODEL,
        max_tokens=8,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(
        b.text for b in resp.content if getattr(b, "type", None) == "text"
    ).strip().lower()
    for name in ("doctrinal", "narrative", "navigational"):
        if name in text:
            return name
    return None
