"""Grounding guards for QA answers: enforcement trigger + quote verification.

Builds on the EXISTING verbatim-splice mechanism (schemas.splice_qa_citations),
NOT the Citations API. See RFC-014 (Grounding decision, amended 2026-07-09).
"""
from __future__ import annotations

_MIN_SUBSTANTIVE_CHARS = 200


def _body_len(response: dict) -> int:
    fr = (response.get("framing") or "").strip()
    fps = response.get("framingParagraphs") or []
    if not isinstance(fps, list):
        fps = []
    return len(fr) + sum(len((p or "").strip()) for p in fps)


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


def enforce_qa(first: dict, *, passages_supplied: int, regenerate) -> dict:
    """Return `first`, or a regenerated response if `first` was under-cited.

    One retry only. The retry is accepted only if it actually has citations;
    otherwise the original is kept (never loop, never make it worse). Any
    exception from `regenerate` yields `first`. Caller wires `regenerate` to a
    second LLM call whose system/user prompt carries CITE_HARDER_SUFFIX.
    """
    if not is_under_cited(first, passages_supplied=passages_supplied):
        return first
    try:
        retry = regenerate()
    except Exception:
        return first
    if retry and retry.get("citations"):
        return retry
    return first
