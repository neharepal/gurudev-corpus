"""
Unit tests for conversational follow-up support in prompts.py.

Tests that:
  1. build_user_message with history=None / [] behaves exactly as before.
  2. build_user_message with history renders a <conversation_history> block
     and the don't-repeat-passages instruction.
  3. build_conversation_history_block correctly formats turns and cited passages.
  4. History with no cited_passages still renders the question.
  5. Multiple prior turns all appear in the transcript.

Corpus-free: no load_corpus(), no embeddings, no live server.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prompts import build_user_message, build_conversation_history_block

# ---------------------------------------------------------------------------
# Minimal chunk fixture — just enough for format_chunks_for_prompt to work.
# ---------------------------------------------------------------------------

CHUNKS = [
    {
        "meta": {
            "kind": "canonical",
            "language": "en",
            "title": "Pathway to God in Hindi Literature",
            "author": "gurudev_ranade",
        },
        "text": "The soul must learn to stand alone in God.",
        "cos_score": 0.9,
        "mmr_score": 0.85,
    },
]


# ---------------------------------------------------------------------------
# build_conversation_history_block
# ---------------------------------------------------------------------------


def test_history_block_empty_when_no_history():
    assert build_conversation_history_block(None) == ""
    assert build_conversation_history_block([]) == ""


def test_history_block_single_turn_with_cited_passages():
    history = [
        {
            "question": "What is Bhakti?",
            "cited_passages": [
                {"workTitle": "Pathway to God", "location": "Chapter 3"},
                {"workTitle": "Mysticism in India", "location": ""},
            ],
        }
    ]
    result = build_conversation_history_block(history)

    assert "[Turn 1]" in result
    assert "What is Bhakti?" in result
    assert "Pathway to God (Chapter 3)" in result
    assert "Mysticism in India" in result
    # Location-less entry should not emit trailing parentheses
    assert "Mysticism in India ()" not in result


def test_history_block_multiple_turns():
    history = [
        {
            "question": "What is Bhakti?",
            "cited_passages": [{"workTitle": "Book A", "location": "p. 10"}],
        },
        {
            "question": "How does one practice naam-sadhana?",
            "cited_passages": [{"workTitle": "Book B", "location": ""}],
        },
    ]
    result = build_conversation_history_block(history)

    assert "[Turn 1]" in result
    assert "[Turn 2]" in result
    assert "What is Bhakti?" in result
    assert "naam-sadhana" in result
    assert "Book A" in result
    assert "Book B" in result


def test_history_block_turn_without_cited_passages():
    history = [{"question": "Who was Bhausaheb?", "cited_passages": []}]
    result = build_conversation_history_block(history)

    assert "[Turn 1]" in result
    assert "Who was Bhausaheb?" in result
    # No "Passages already cited:" line when there are no citations
    assert "Passages already cited" not in result


# ---------------------------------------------------------------------------
# build_user_message — backward compatibility (no history)
# ---------------------------------------------------------------------------


def test_build_user_message_no_history_unchanged():
    """Single-turn path: output must match the legacy format exactly."""
    msg = build_user_message(CHUNKS, "What is self-surrender?")

    assert "<retrieved_passages>" in msg
    assert "<question>" in msg
    assert "What is self-surrender?" in msg
    # Should NOT include conversation history block or instruction
    assert "<conversation_history>" not in msg
    assert "<instruction>" not in msg


def test_build_user_message_empty_list_history_unchanged():
    """Passing an empty list should behave the same as passing None."""
    msg_none = build_user_message(CHUNKS, "What is self-surrender?", history=None)
    msg_empty = build_user_message(CHUNKS, "What is self-surrender?", history=[])
    assert msg_none == msg_empty
    assert "<conversation_history>" not in msg_empty
    assert "<instruction>" not in msg_empty


# ---------------------------------------------------------------------------
# build_user_message — with history
# ---------------------------------------------------------------------------


def test_build_user_message_with_history_includes_transcript():
    history = [
        {
            "question": "What is Bhakti?",
            "cited_passages": [
                {"workTitle": "Pathway to God", "location": "Chapter 3"}
            ],
        }
    ]
    msg = build_user_message(CHUNKS, "How is Bhakti related to Jnana?", history=history)

    assert "<retrieved_passages>" in msg
    assert "<conversation_history>" in msg
    assert "</conversation_history>" in msg
    assert "What is Bhakti?" in msg
    assert "Pathway to God" in msg
    assert "<question>" in msg
    assert "How is Bhakti related to Jnana?" in msg


def test_build_user_message_with_history_includes_two_case_instruction():
    """The follow-up instruction covers TWO cases: (a) bring new material
    when the user asks for more, and (b) operate on prior citations when the
    user asks to translate / summarize / elaborate on them. The 'don't repeat'
    guidance stays but is scoped to case (a)."""
    history = [
        {
            "question": "What is Bhakti?",
            "cited_passages": [
                {"workTitle": "Pathway to God", "location": "p. 42"}
            ],
        }
    ]
    msg = build_user_message(CHUNKS, "Follow-up question", history=history)

    assert "<instruction>" in msg
    assert "</instruction>" in msg
    # Case (a): keep the don't-repeat + bring-new guidance.
    assert "bring NEW material" in msg
    assert "nothing new to add" in msg
    assert "do NOT repeat passages" in msg
    # Case (b): operate on prior citations (translate / summarize / elaborate).
    assert "translate" in msg
    assert "summarize" in msg
    # Case (b) design: emit citations whose body comes from prior turn
    # and paraphrase carries the translation/summary. passage/quoteStart/End
    # empty signals the splicer to leave model body untouched (schemas.py:639
    # "genuine verbatim body ... leave it untouched"). Never graft prior-
    # turn output onto unrelated retrieved passages.
    assert "OVERRIDES THE STANDARD CITATION CONTRACT" in msg
    assert '`quote.passage` = ""' in msg
    assert '`quote.quoteStart` = "" and `quote.quoteEnd` = ""' in msg
    assert "graft" in msg.lower() or "Grafting" in msg
    # verbatim ORIGINAL body from history is required (case b.1 keeps side-
    # by-side cards; b.2 SUMMARIZE mode is prose-only via framingParagraphs).
    assert "verbatim ORIGINAL passage from" in msg
    assert "your translation of that body" in msg
    # kind + author fallback (in case history is missing them).
    assert "kind=\"canonical\"" in msg


def test_build_user_message_history_ordering():
    """The conversation transcript must appear BEFORE the current question."""
    history = [
        {"question": "Prior question", "cited_passages": []},
    ]
    msg = build_user_message(CHUNKS, "Current question", history=history)

    history_pos = msg.index("<conversation_history>")
    question_pos = msg.index("<question>")
    assert history_pos < question_pos, (
        "conversation_history must appear before the current <question>"
    )


def test_build_user_message_retrieved_passages_always_first():
    """Retrieved passages always appear first, even with history."""
    history = [
        {"question": "Prior question", "cited_passages": []},
    ]
    msg = build_user_message(CHUNKS, "Current question", history=history)

    passages_pos = msg.index("<retrieved_passages>")
    history_pos = msg.index("<conversation_history>")
    assert passages_pos < history_pos, (
        "<retrieved_passages> must appear before <conversation_history>"
    )


def test_build_user_message_multiple_history_turns():
    """All prior turns appear in the transcript."""
    history = [
        {
            "question": "Turn 1 question",
            "cited_passages": [{"workTitle": "Book A", "location": ""}],
        },
        {
            "question": "Turn 2 question",
            "cited_passages": [{"workTitle": "Book B", "location": "p. 5"}],
        },
    ]
    msg = build_user_message(CHUNKS, "Turn 3 question", history=history)

    assert "Turn 1 question" in msg
    assert "Turn 2 question" in msg
    assert "Book A" in msg
    assert "Book B" in msg
    # Current question also present
    assert "Turn 3 question" in msg


# ---------------------------------------------------------------------------
# Citation BODY rendering — enables translate/summarize follow-ups
# ---------------------------------------------------------------------------


def test_history_block_renders_citation_body_when_present():
    """When a cited passage carries a `body`, it must be rendered verbatim in
    the history block so the model can translate / summarize / elaborate on
    it in a follow-up. kind + author (when present) render on a `[…]` meta
    line so the model can copy them into case-(b) prior-turn citations."""
    history = [
        {
            "question": "What are the key messages in Amar Sandesh Sudha?",
            "cited_passages": [
                {
                    "workTitle": "Amar Sandesh Sudha",
                    "location": "p. 12",
                    "kind": "canonical",
                    "author": "gurudev_ranade",
                    "body": "अखंड नामस्मरण करावे, हेच खरे परमार्थ.",
                },
                {
                    "workTitle": "Amar Sandesh Sudha",
                    "location": "p. 34",
                    "kind": "canonical",
                    "author": "gurudev_ranade",
                    "body": "गुरुकृपेनेच आत्मसाक्षात्कार होतो.",
                },
            ],
        }
    ]
    block = build_conversation_history_block(history)

    assert "Amar Sandesh Sudha" in block
    assert "p. 12" in block
    assert "अखंड नामस्मरण करावे" in block
    assert "गुरुकृपेनेच आत्मसाक्षात्कार होतो" in block
    # Verbose form uses enumerated citations and the "—" location separator.
    assert "(1) Amar Sandesh Sudha — p. 12" in block
    assert "(2) Amar Sandesh Sudha — p. 34" in block
    # Meta line lets the model copy kind + author into case-(b) citations.
    assert "[kind=canonical, author=gurudev_ranade]" in block


def test_history_block_falls_back_to_compact_form_when_no_body():
    """Backwards compatibility: if none of the cited passages carry a `body`,
    we emit the old single-line compact form to keep prompt cost minimal."""
    history = [
        {
            "question": "What is Bhakti?",
            "cited_passages": [
                {"workTitle": "Pathway to God", "location": "Chapter 3"},
                {"workTitle": "Mysticism in India", "location": ""},
            ],
        }
    ]
    block = build_conversation_history_block(history)

    # Compact form — one line with semicolons, no per-citation indentation.
    assert "Passages already cited: Pathway to God (Chapter 3)" in block
    assert "Mysticism in India" in block
    # The verbose enumerator should NOT appear when no body is present.
    assert "(1) Pathway to God" not in block


def test_history_block_mixed_bodies_uses_verbose_form():
    """If ANY passage in a turn has a body, that turn's citations render in
    the verbose form (bodies are useful; downgrading them all to compact
    would drop the body signal)."""
    history = [
        {
            "question": "What is Bhakti?",
            "cited_passages": [
                {"workTitle": "Book A", "location": "p. 1",
                 "body": "A verbatim quote from Book A."},
                {"workTitle": "Book B", "location": "p. 2"},  # no body
            ],
        }
    ]
    block = build_conversation_history_block(history)
    # Verbose form for both.
    assert "(1) Book A — p. 1" in block
    assert "A verbatim quote from Book A." in block
    assert "(2) Book B — p. 2" in block


def test_history_block_multiline_body_preserves_lines():
    """Multi-line citation bodies (common for verse) must keep their line
    breaks in the transcript."""
    history = [
        {
            "question": "Abhang example",
            "cited_passages": [
                {
                    "workTitle": "Tukaram Vachanamrut",
                    "location": "p. 45",
                    "body": "अभंग पहिली ओळ\nअभंग दुसरी ओळ\nअभंग तिसरी ओळ",
                },
            ],
        }
    ]
    block = build_conversation_history_block(history)

    # Every line of the body must survive.
    assert "अभंग पहिली ओळ" in block
    assert "अभंग दुसरी ओळ" in block
    assert "अभंग तिसरी ओळ" in block


def test_build_user_message_carries_bodies_through_to_history_block():
    """Integration: the assembled user message includes citation bodies from
    the history payload, so a translate follow-up can quote them."""
    history = [
        {
            "question": "What are the key messages in Amar Sandesh Sudha?",
            "cited_passages": [
                {"workTitle": "Amar Sandesh Sudha", "location": "p. 12",
                 "body": "अखंड नामस्मरण करावे, हेच खरे परमार्थ."},
            ],
        }
    ]
    msg = build_user_message(
        CHUNKS, "Translate above passages to English.", history=history,
    )
    assert "<conversation_history>" in msg
    assert "अखंड नामस्मरण करावे" in msg
    # And the current translate question is present.
    assert "Translate above passages to English." in msg


# ── Mukund's session (2026-07-19) — three new failure modes to prevent ─────

def test_output_shape_prescription_for_summarize_follow_up():
    """Mukund #3: the LLM put a 4.8k-char summary in `synthesis` (meant for a
    1-2 sentence closer) → frontend rendered it small and Mukund said 'where
    is the summary?'. The follow-up prompt MUST prescribe where the
    operation output goes so the model can't accidentally hide the answer
    in the wrong field."""
    history = [{"question": "Summarize Ranade's evolution-of-thought essay",
                "cited_passages": [{"workTitle": "Contemporary Indian Philosophy",
                                     "location": "essay",
                                     "body": "Some prior passage."}]}]
    msg = build_user_message(CHUNKS, "Expand it in plain language", history=history)
    # The instruction must name the fields and be prescriptive about where
    # multi-paragraph output goes.
    assert "framingParagraphs" in msg
    assert "synthesis" in msg
    # Must forbid using `synthesis` as the main body of the answer.
    assert "synthesis" in msg and (
        "not put the body" in msg.lower()
        or "closing" in msg.lower()
        or "not the main" in msg.lower()
    )


def test_sticky_style_directives_from_prior_turns():
    """Mukund #1: he said 'don't reproduce passages' at turn N. The LLM
    honored it that turn, forgot it at N+1 and re-added verbatim citations.
    The prompt MUST tell the model to look through <conversation_history>
    for user style directives and honor them in subsequent turns even when
    not repeated."""
    history = [{"question": "Please don't reproduce passages; give a plain "
                            "summary of the essay",
                "cited_passages": [{"workTitle": "Contemporary Indian Philosophy",
                                     "location": "essay",
                                     "body": "Prior body."}]}]
    msg = build_user_message(CHUNKS, "Now expand it", history=history)
    # The instruction must explicitly ask the model to honor sticky style
    # preferences from earlier turns.
    m = msg.lower()
    assert "sticky" in m or "carry" in m or "honor" in m or "preserve" in m
    assert "prior turn" in m or "earlier turn" in m or "previous turn" in m
    # And must give concrete examples so the model knows what to look for.
    assert '"don' in m or "don't reproduce" in m or "in plain language" in m or "style" in m


def test_empty_body_guard_for_case_b():
    """Mukund #2: the LLM emitted a 212-char 'here is a summary' framing
    followed by 0 chars in framingParagraphs / synthesis / citations. The
    prompt must forbid this shape — if you say 'here is X', X must appear."""
    history = [{"question": "Summarize the essay",
                "cited_passages": [{"workTitle": "Some Work", "location": "1",
                                     "body": "Body."}]}]
    msg = build_user_message(CHUNKS, "Try again in plain language", history=history)
    m = msg.lower()
    # Warn against the "Here is a summary" + no body pattern.
    assert "here is a summary" in m or "if you announce content, deliver it" in m
    # AND require explicit non-emission rule for the incomplete shape.
    assert "incomplete" in m and "do not emit" in m
