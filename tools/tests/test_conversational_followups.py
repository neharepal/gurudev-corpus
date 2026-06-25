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


def test_build_user_message_with_history_includes_dont_repeat_instruction():
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
    # Key instruction phrases
    assert "Do NOT cite passages already shown" in msg
    assert "bring NEW material" in msg
    assert "nothing new to add" in msg


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
