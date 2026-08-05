"""Query rewriting + HyDE for retrieval (mirrors query_translation.py).

A bare/short query lands in a sparse embedding region; a full-prose rewrite or
a hypothetical answer paragraph (HyDE) moves the search ANCHOR into the
descriptive-prose neighborhood where the answer actually lives — the effect we
already observe when a user asks a full question. Retrieval embeds these
ADDITIONAL query strings alongside the original (BM25 on the original stays the
exact-match backbone). Cached Haiku; any failure returns None (no-op).
"""
from __future__ import annotations
import re
import unicodedata
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


# Straight, smart-double, and low-9 quotation marks in one class. Single
# quotes (') are intentionally excluded — they collide with English
# apostrophes ("Gurudev's writings") and would fire on every possessive.
_QUOTE_CHARS = "\"“”„"  # " " " „
_QUOTED_SPAN_RE = re.compile(
    rf"[{_QUOTE_CHARS}]([^{_QUOTE_CHARS}]{{2,}}?)[{_QUOTE_CHARS}]"
)

# Stopwords that add no discriminative value to a book-title match. Dropped
# during normalization so "Bhagavad Gita as a Philosophy of God Realization"
# and "The Bhagavadgita Philosophy of God-Realisation" collide.
_TITLE_STOPWORDS = frozenset({
    "the", "a", "an", "of", "to", "in", "on", "as", "and", "is", "for",
    "at", "by", "with", "from", "into", "onto",
})

# British ↔ American spelling collapses (Ranade titles use British `-sation`
# / `-ise`; users often type American `-zation` / `-ize`). Longest-first so
# a substring rewrite doesn't accidentally chop a longer match.
_SPELLING_NORMALIZE = [
    ("sation", "zation"),
    ("isation", "ization"),
    ("ised", "ized"),
    ("iser", "izer"),
    ("ising", "izing"),
    ("isable", "izable"),
]


def _extract_quoted_spans(query: str) -> list[str]:
    """Return the content of every double-quoted span in the query
    (straight " ", curly " " " ", or German „ "). Interior whitespace is
    normalized to single spaces and the span is stripped."""
    spans = []
    for m in _QUOTED_SPAN_RE.finditer(query or ""):
        s = re.sub(r"\s+", " ", m.group(1)).strip()
        if len(s) >= 2:
            spans.append(s)
    return spans


def _normalize_title_key(s: str) -> str:
    """Fold a title (or user-quoted claim) to a single lowercase alphanumeric
    string with:
      • diacritics dropped (Bhāgavadgītā → Bhagavadgita)
      • common British→American spelling normalized (realisation → realization)
      • stopwords + articles dropped (the, a, of, as, …)
      • all whitespace + punctuation + hyphens collapsed out

    The result is a length-agnostic "fingerprint" that lets us bidirectionally
    substring-match user claims against catalog titles even when the two
    disagree on word-splits (`Bhagavad Gita` ↔ `Bhagavadgita`), hyphenation
    (`God Realization` ↔ `God-Realisation`), and diacritics/case.
    """
    if not s:
        return ""
    # Decompose Latin diacritics and drop the combining marks (Bhāgavadgītā
    # → Bhagavadgita). Devanagari conjuncts survive because NFKD does not
    # decompose them into base + combining halants that we'd want removed.
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    # British → American spelling collapse (Latin-side; harmless on Devanagari).
    for old, new in _SPELLING_NORMALIZE:
        s = s.replace(old, new)
    # Tokenize on non-word characters (Unicode-aware: keeps Devanagari,
    # Bengali, Greek, etc. as word chars), drop English stopwords, rejoin
    # as one blob.
    tokens = [t for t in re.split(r"[^\w]+", s) if t and t not in _TITLE_STOPWORDS]
    return "".join(tokens)


def _match_quoted_span_to_works(span: str, catalog_titles: list) -> list[str]:
    """Given a quoted span and a list of (title, work_id) pairs, return
    the set of work_ids the span could refer to. Match is normalized (see
    _normalize_title_key) and bidirectional: span-fingerprint ⊂ title-fp
    (user typed part of the title) OR title-fp ⊂ span-fp (user quoted a
    phrase that contains the title). A minimum-key-length gate (5 chars)
    prevents empty or trivial keys from matching everything."""
    span_key = _normalize_title_key(span)
    if len(span_key) < 5:
        return []
    hits = set()
    for title, wid in catalog_titles:
        title_key = _normalize_title_key(title)
        if len(title_key) < 5:
            continue
        if span_key in title_key or title_key in span_key:
            hits.add(wid)
    return sorted(hits)


def extract_mentioned_work(query: str, known_works: list) -> Optional[dict]:
    """Detect which specific work (if any) a sadhak wants retrieval scoped
    to. Two deterministic tiers, no LLM.

    1. QUOTED PASS (highest precision, explicit user intent). Any
       double-quoted span in the query is treated as a title claim and
       matched bidirectionally against `title` / `title_en` /
       `title_translit`. Exactly one matching work → scope, method="quoted".
       Multiple matching works → no scope (ambiguous, logged as candidates).
    2. SUBSTRING PASS (unquoted, weaker signal, backwards-compat).
       Case-insensitive substring match of every ≥8-char title against
       the query, longest-first. Exactly one work matches → scope,
       method="substring".

    An earlier revision of this detector had an LLM fallback for the
    zero-hit / paraphrase case (ADR-018). Post-launch evidence showed the
    LLM misfires on topical queries ("views on Bhakti" → "Life and
    Philosophy"): it has no signal to distinguish a paraphrased title
    from a topical question. The revised design removes the LLM entirely
    — users who want scope on a paraphrase or cross-lingual variant now
    quote the title explicitly, which is a hard signal.

    Args:
        query: the user's raw question.
        known_works: list of dicts with at least {work_id, title, title_en,
            title_translit}. Typically STATE.works_catalog.

    Returns:
        {
          "work_id": "amar-sandesh-sudha",
          "title":   "Amar Sandesh Sudha",
          "method":  "quoted" | "substring" | "ambiguous",
          "candidates": [work_id, ...],   # populated when method="ambiguous"
        }
        or None if no work is referenced.
    """
    q = (query or "").strip()
    if not q or not known_works:
        return None

    # Build (title, work_id) pairs, deduped. Two catalogs: (a) FULL for the
    # quoted tier — no length threshold, so a quoted "Vedant" can match a
    # short-titled work; (b) LONG (≥8 chars) for the unquoted substring
    # tier where short titles produce topical false positives.
    all_titled: list[tuple[str, str]] = []
    long_titled: list[tuple[str, str]] = []
    seen = set()
    for w in known_works:
        wid = w.get("work_id") if isinstance(w, dict) else None
        if not wid:
            continue
        for f in ("title", "title_en", "title_translit"):
            v = w.get(f) if isinstance(w, dict) else None
            if not v or not isinstance(v, str):
                continue
            v = v.strip()
            if len(v) < 2:
                continue
            key = (v.lower(), wid)
            if key in seen:
                continue
            seen.add(key)
            all_titled.append((v, wid))
            if len(v) >= 8:
                long_titled.append((v, wid))

    # Longest first so "Pathway to God in the Vedas" wins over "Pathway to
    # God" when both are substrings of the same query fragment.
    all_titled.sort(key=lambda x: -len(x[0]))
    long_titled.sort(key=lambda x: -len(x[0]))

    # ── TIER 1: quoted spans ────────────────────────────────────────────
    quoted_spans = _extract_quoted_spans(q)
    if quoted_spans:
        matched_ids: set[str] = set()
        matched_title_for_id: dict[str, str] = {}
        for span in quoted_spans:
            hits = _match_quoted_span_to_works(span, all_titled)
            for wid in hits:
                matched_ids.add(wid)
                # Prefer the first (longest) title we can attribute to wid
                # so the log message is human-friendly.
                if wid not in matched_title_for_id:
                    matched_title_for_id[wid] = next(
                        (t for t, w in all_titled if w == wid), wid
                    )
        if len(matched_ids) == 1:
            wid = next(iter(matched_ids))
            return {"work_id": wid, "title": matched_title_for_id[wid],
                    "method": "quoted", "candidates": [wid]}
        if len(matched_ids) > 1:
            return {"work_id": None, "title": None, "method": "ambiguous",
                    "candidates": sorted(matched_ids)}
        # Quoted span present but matched no work — fall through to
        # substring tier. If that also fails the user gets an unscoped
        # answer, which is safer than pretending a random work was picked.

    # ── TIER 2: unquoted substring ──────────────────────────────────────
    # Normalize both sides (see _normalize_title_key) so human queries that
    # skip diacritics, use different word-splits, or hit British/American
    # spelling still match the title. The `long_titled` filter (raw ≥ 8
    # chars) is the guard against topical false positives on short titles.
    q_key = _normalize_title_key(q)
    substring_hits: list[tuple[str, str]] = []
    matched_work_ids: set[str] = set()
    for title, wid in long_titled:
        title_key = _normalize_title_key(title)
        if not title_key:
            continue
        if title_key in q_key and wid not in matched_work_ids:
            substring_hits.append((title, wid))
            matched_work_ids.add(wid)

    if len(substring_hits) == 1:
        title, wid = substring_hits[0]
        return {"work_id": wid, "title": title, "method": "substring",
                "candidates": [wid]}
    if len(substring_hits) > 1:
        return {"work_id": None, "title": None, "method": "ambiguous",
                "candidates": [wid for _t, wid in substring_hits]}
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
