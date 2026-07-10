"""Grounding guards for QA answers: enforcement trigger + quote verification.

Builds on the EXISTING verbatim-splice mechanism (schemas.splice_qa_citations),
NOT the Citations API. See RFC-014 (Grounding decision, amended 2026-07-09).
"""
from __future__ import annotations
from typing import Any

_MIN_SUBSTANTIVE_CHARS = 200


def _body_len(response: dict) -> int:
    fr = (response.get("framing") or "").strip()
    fps = response.get("framingParagraphs") or []
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
