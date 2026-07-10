"""
Tests that each mode's system prompt contains voice/persona guidance
and still contains its existing structural instructions.
"""
import prompts


# ---------------------------------------------------------------------------
# Voice-presence checks — a stable keyword introduced in the VOICE section
# ---------------------------------------------------------------------------

def test_qa_prompt_has_voice_section():
    assert "Voice and persona" in prompts.SYSTEM_PROMPT_QA


def test_pravachan_prompt_has_voice_section():
    assert "Voice and persona" in prompts.SYSTEM_PROMPT_PRAVACHAN


def test_reading_prompt_has_voice_section():
    assert "Voice and persona" in prompts.SYSTEM_PROMPT_READING


# The prompts must use "Gurudev" as the canonical name (not bare "Ranade")
def test_qa_prompt_uses_gurudev_name():
    assert "Gurudev" in prompts.SYSTEM_PROMPT_QA


def test_pravachan_prompt_uses_gurudev_name():
    assert "Gurudev" in prompts.SYSTEM_PROMPT_PRAVACHAN


def test_reading_prompt_uses_gurudev_name():
    assert "Gurudev" in prompts.SYSTEM_PROMPT_READING


# Guard: each voice section explicitly forbids using bare "Ranade" as a
# reference name. We search for 'never' adjacent to 'Ranade' (ignoring the
# trailing punctuation character after the closing quote, which varies).
def test_qa_voice_section_forbids_bare_ranade():
    assert 'never "Ranade' in prompts.SYSTEM_PROMPT_QA


def test_pravachan_voice_section_forbids_bare_ranade():
    assert 'never "Ranade' in prompts.SYSTEM_PROMPT_PRAVACHAN


def test_reading_voice_section_forbids_bare_ranade():
    assert 'never "Ranade' in prompts.SYSTEM_PROMPT_READING


# ---------------------------------------------------------------------------
# Structural-instruction preservation — key phrases from before the change
# ---------------------------------------------------------------------------

def test_qa_still_has_output_contract():
    assert "emit_qa_response" in prompts.SYSTEM_PROMPT_QA


# NOTE: the QA doctrinal/meta question-type classification step was removed
# when ADR-010's split was superseded (2026-07-08) in favor of a single
# unified quote-and-synthesize mode — there is no longer a "classify the
# question" step in SYSTEM_PROMPT_QA, so the old test asserting it is deleted.


def test_qa_still_has_honesty_rule():
    assert "Honesty" in prompts.SYSTEM_PROMPT_QA


def test_qa_still_has_framing_field_guide():
    assert "`framing`" in prompts.SYSTEM_PROMPT_QA


def test_qa_still_has_synthesis_field_guide():
    assert "`synthesis`" in prompts.SYSTEM_PROMPT_QA


def test_pravachan_still_has_output_contract():
    assert "emit_pravachan_response" in prompts.SYSTEM_PROMPT_PRAVACHAN


def test_pravachan_still_has_examples_field():
    assert "`examples`" in prompts.SYSTEM_PROMPT_PRAVACHAN


def test_pravachan_still_has_honesty_rule():
    # Pravachan no longer has a standalone "# Honesty" heading (its honesty
    # guidance now lives under "# Same rules as Q&A mode apply"), but the
    # no-invention rule itself is still real current behavior — assert on it.
    assert "Never invent quotes, dates, or details" in prompts.SYSTEM_PROMPT_PRAVACHAN


def test_reading_still_has_output_contract():
    assert "emit_reading_response" in prompts.SYSTEM_PROMPT_READING


def test_reading_still_has_framing_field_guide():
    assert "`framing`" in prompts.SYSTEM_PROMPT_READING


def test_reading_still_has_length_constraint():
    assert "SHORT" in prompts.SYSTEM_PROMPT_READING


# ---------------------------------------------------------------------------
# get_system_prompt selector still works
# ---------------------------------------------------------------------------

def test_get_system_prompt_returns_correct_prompts():
    # get_system_prompt now prepends an "# ANSWER LANGUAGE" header (the UI
    # toggle enforcement) ahead of the mode's base prompt, so the result is
    # no longer identical to the bare SYSTEM_PROMPT_* constant — it ends with it.
    assert prompts.get_system_prompt("qa").endswith(prompts.SYSTEM_PROMPT_QA)
    assert prompts.get_system_prompt("pravachan").endswith(prompts.SYSTEM_PROMPT_PRAVACHAN)
    assert prompts.get_system_prompt("reading").endswith(prompts.SYSTEM_PROMPT_READING)


def test_get_system_prompt_raises_for_unknown_mode():
    import pytest
    with pytest.raises(ValueError, match="Unknown mode"):
        prompts.get_system_prompt("bogus")


# ---------------------------------------------------------------------------
# Language-detection: the UI `lang` toggle ALWAYS governs the answer language.
#
# POLICY CHANGE from the old "answer in the language of the user's question"
# behavior: the answer/paraphrase language is now solely and always governed
# by the reader's `lang` toggle (see get_system_prompt's prepended "ANSWER
# LANGUAGE" header and each mode's "# Language of response" section). The
# question's/topic's own language is explicitly irrelevant now. The old
# "instructs_question_language" and "lang_is_fallback" tests asserted a
# premise (question-language matching, `lang` as mere fallback hint) that no
# longer exists at all — those are deleted below rather than "fixed", since
# there's no current equivalent to port them to. The toggle-governs and
# paraphrase tests are updated in place to the current, real behavior.
# ---------------------------------------------------------------------------

# Each prompt must state that the reader's `lang` toggle governs the answer
# language, and that the question's/topic's own language does NOT.
def test_qa_prompt_toggle_governs_answer_language():
    assert "The reader's `lang` toggle governs; the question's own language does not." in prompts.SYSTEM_PROMPT_QA


def test_pravachan_prompt_toggle_governs_answer_language():
    assert "The reader's `lang` toggle governs; the topic's own language does not." in prompts.SYSTEM_PROMPT_PRAVACHAN


def test_reading_prompt_toggle_governs_answer_language():
    assert "The reader's `lang` toggle governs; the question's own language does not." in prompts.SYSTEM_PROMPT_READING


# The paraphrase/gloss rule keys to the answer language (the `lang` toggle),
# not to the question's language.
def test_qa_paraphrase_keyed_to_answer_language():
    assert "quote's language differs from the answer language" in prompts.SYSTEM_PROMPT_QA


def test_pravachan_paraphrase_keyed_to_answer_language():
    # Two places in Pravachan prompt reference this.
    assert prompts.SYSTEM_PROMPT_PRAVACHAN.count("quote's language differs from the answer language") == 2


def test_reading_paraphrase_keyed_to_answer_language():
    assert "in a language other than the answer language" in prompts.SYSTEM_PROMPT_READING


# ---------------------------------------------------------------------------
# Confirm verbatim-quote rule is NOT changed (ADR-007 still intact)
# ---------------------------------------------------------------------------

def test_qa_verbatim_rule_intact():
    assert "VERBATIM" in prompts.SYSTEM_PROMPT_QA


def test_pravachan_verbatim_rule_intact():
    assert "verbatim" in prompts.SYSTEM_PROMPT_PRAVACHAN


def test_reading_verbatim_rule_intact():
    assert "verbatim" in prompts.SYSTEM_PROMPT_READING.lower()
