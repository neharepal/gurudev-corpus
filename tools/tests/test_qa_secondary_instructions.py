"""Guards on the QA system prompt so we don't regress the
primary-ask + secondary-instructions reading rule added by RFC-019
(2026-07-22) in response to the "List of places Gurudev visited. Only
list in bullet points." misfire.

The rules the LLM must be told to follow:
  1. Read every user message as (a) a primary factual ask + (b) zero or
     more secondary instructions (format / length / ordering / scope /
     exclusions / language / comparison).
  2. Honor secondary instructions to the extent the retrieved passages
     allow; place the honoring answer in `synthesis` (markdown-capable).
  3. If an instruction cannot be honored, say so in one line — never
     pad, invent dates, or manufacture items.
  4. Citations are always shown regardless of format/length asks.
  5. Passage-letter link convention `- item (A)` for click-to-cite.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from prompts import SYSTEM_PROMPT_QA  # noqa: E402


def test_prompt_declares_primary_plus_secondary_reading():
    """The prompt must name the primary/secondary decomposition and
    enumerate at least three instruction types the model should watch for."""
    p = SYSTEM_PROMPT_QA
    p_l = p.lower()
    # The section header should exist so future edits can find it.
    assert "read the whole question" in p_l, (
        "prompt should declare a top-level rule about reading the whole "
        "user message, not just the topic"
    )
    # It must name at least three of the seven instruction types.
    types = ["format", "length", "ordering", "scope", "exclusion", "language", "comparison"]
    hits = [t for t in types if t in p_l]
    assert len(hits) >= 3, (
        f"prompt should enumerate at least three secondary-instruction types; "
        f"found only: {hits}"
    )


def test_prompt_places_user_shaped_answer_in_synthesis():
    """The `synthesis` field is now the user-shaped answer body — the
    prompt must say so, so the LLM knows where bullets/tables/short
    answers live."""
    p = SYSTEM_PROMPT_QA
    p_l = p.lower()
    # Explicit mention of synthesis as the target for user-shaped answers.
    assert "synthesis" in p_l
    # At least one of the concrete examples (bullet / bulleted list) must
    # be in the prompt so the model knows synthesis can carry a list.
    assert any(w in p_l for w in ("bulleted list", "bullets", "- ")), (
        "prompt should give at least one concrete example of a list format "
        "living in synthesis"
    )
    # Markdown must be explicitly allowed in synthesis.
    assert "markdown" in p_l


def test_prompt_bans_padding_and_invention_to_satisfy_format():
    """If the user asks for 10 items but the passages support only 4, the
    model must not invent 6 more. Anti-hallucination rule."""
    p = SYSTEM_PROMPT_QA
    p_l = p.lower()
    # The rule must be explicit — one of these phrasings should be present.
    assert any(
        phrase in p_l
        for phrase in ("never pad", "do not pad", "no padding")
    ), "prompt should explicitly ban padding to satisfy an item-count ask"
    assert any(
        phrase in p_l
        for phrase in ("invent dates", "manufacture items", "invent facts")
    ), "prompt should explicitly ban inventing dates/items to satisfy an ordering/count ask"


def test_prompt_protects_citations_from_brevity_asks():
    """A user saying 'in one sentence' shrinks synthesis, not citations —
    citations are the evidence and must always render."""
    p = SYSTEM_PROMPT_QA
    p_l = p.lower()
    # Look for the invariant that citations render regardless of format.
    assert (
        "citations are always shown" in p_l
        or "citations still render" in p_l
        or "always shown as evidence" in p_l
    ), (
        "prompt should state that citations are always shown regardless of "
        "any format or length instruction"
    )


def test_prompt_teaches_partial_honoring_disclosure():
    """When the model can't fully honor an instruction, it must say so in
    one short honest line — not silently drop it."""
    p = SYSTEM_PROMPT_QA
    p_l = p.lower()
    # The disclosure convention must be present.
    assert any(
        phrase in p_l
        for phrase in ("cannot be fully honored", "not fully honored", "cannot be honored")
    ), "prompt should tell the model to disclose partial honoring"


def test_prompt_teaches_passage_letter_link_convention():
    """Items in a list that map to a citation end with the passage letter
    in parens, e.g. `- Nimbal (A)`. The frontend wires the letter to a
    click-to-cite anchor."""
    p = SYSTEM_PROMPT_QA
    # Look for the passage-letter parens convention — accept any A/B/E
    # example that shows the pattern.
    assert any(
        f"({letter})" in p for letter in ("A", "B", "E")
    ), (
        "prompt should show at least one worked example of the "
        "`- item (A)` passage-letter link convention"
    )


def test_motivating_anti_example_present():
    """The 'List of places' misfire should be referenced by name so
    future maintainers know why this rule exists."""
    p = SYSTEM_PROMPT_QA
    p_l = p.lower()
    assert "list of places" in p_l, (
        "prompt should reference the 2026-07-22 'List of places' misfire "
        "as the motivating anti-example"
    )
