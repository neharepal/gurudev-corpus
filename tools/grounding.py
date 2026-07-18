"""Grounding guards for QA answers: enforcement trigger + quote verification.

Builds on the EXISTING verbatim-splice mechanism (schemas.splice_qa_citations),
NOT the Citations API. See RFC-014 (Grounding decision, amended 2026-07-09).
"""
from __future__ import annotations
import unicodedata

_MIN_SUBSTANTIVE_CHARS = 200


def _body_len(response: dict) -> int:
    fr = (response.get("framing") or "").strip()
    syn = (response.get("synthesis") or "").strip()
    fps = response.get("framingParagraphs") or []
    if not isinstance(fps, list):
        fps = []
    return len(fr) + len(syn) + sum(len((p or "").strip()) for p in fps)


def is_under_cited(response: dict, *, passages_supplied: int) -> bool:
    """True when a substantive QA answer cites nothing though passages existed.

    Substantive = combined framing/framingParagraphs length >= 200 chars, so a
    short "not covered" note is never flagged. Requires passages_supplied >= 1
    (nothing to cite otherwise). This is the enforcement trigger.
    """
    if passages_supplied < 1:
        return False
    if response.get("citations"):
        return False
    return _body_len(response) >= _MIN_SUBSTANTIVE_CHARS


CITE_HARDER_SUFFIX = (
    "\n\nIMPORTANT: Your previous attempt made claims without citing any of the "
    "supplied passages. You MUST ground this answer: cite the relevant passages "
    "by reference (passage letter + quoteStart/quoteEnd) for the claims you make. "
    "If a passage touches the topic even partially, quote it rather than "
    "paraphrasing uncited. Do not answer from general knowledge alone."
)


def enforce_qa(first: dict, *, passages_supplied: int, regenerate,
                has_history: bool = False) -> dict:
    """Return `first`, or a regenerated response if `first` was under-cited.

    One retry only. The retry is accepted only if it actually has citations;
    otherwise the original is kept (never loop, never make it worse). Any
    exception from `regenerate` yields `first`. Caller wires `regenerate` to a
    second LLM call whose system/user prompt carries CITE_HARDER_SUFFIX.

    When `has_history` is True (i.e., this is a follow-up in an ongoing
    conversation), the retry is SKIPPED. The reader has already seen the
    prior turn's citations, and follow-up operations (translate / summarize /
    elaborate on prior passages) legitimately produce zero-citation answers
    per the case-(b) branch of build_user_message. Forcing a cite-harder
    retry there causes the model to graft translations onto unrelated
    retrieved passages (observed 2026-07-18) — worse UX than the empty-
    citations path.
    """
    if has_history:
        return first
    if not is_under_cited(first, passages_supplied=passages_supplied):
        return first
    try:
        retry = regenerate()
    except Exception:
        return first
    if retry and retry.get("citations"):
        return retry
    return first


try:
    from rapidfuzz.fuzz import partial_ratio as _partial_ratio
except Exception:  # rapidfuzz optional — degrade to exact substring
    _partial_ratio = None


def _norm(s) -> str:
    # NFC-normalize (Devanagari matras) + collapse whitespace for robust matching.
    return " ".join(unicodedata.normalize("NFC", str(s) if s else "").split())


def _matches(body: str, source: str, threshold: int) -> bool:
    nb, ns = _norm(body), _norm(source)
    if not nb:
        return True  # empty body handled by caller; treat as non-flag
    if nb in ns:
        return True
    if _partial_ratio is None:
        return False
    return _partial_ratio(nb, ns) >= threshold


def verify_citations(citations: list, label_to_chunk: dict, *, threshold: int = 85) -> list:
    """Return advisory flag records for citations whose body ∉ its source chunk.

    A mismatch means the spliced/stored SOURCE is likely OCR-corrupt (the splice
    already forces body from source) — so this feeds source-repair, not answer
    rejection. Never raises; never blocks the answer.
    """
    flags = []
    for c in citations or []:
        q = (c or {}).get("quote") or {}
        body = q.get("body") or ""
        passage = (q.get("passage") or "").strip()
        if not body.strip():
            continue
        chunk = (label_to_chunk or {}).get(passage)
        if chunk is None:
            flags.append({"passage": passage, "workTitle": q.get("workTitle", ""),
                          "score": 0, "reason": "no source chunk"})
            continue
        source = chunk.get("text") or ""
        if not _matches(body, source, threshold):
            score = 0 if _partial_ratio is None else int(_partial_ratio(_norm(body), _norm(source)))
            flags.append({"passage": passage, "workTitle": q.get("workTitle", ""),
                          "score": score, "reason": "body not found in source"})
    return flags
