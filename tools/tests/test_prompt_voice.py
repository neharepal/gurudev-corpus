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


def test_qa_still_has_classification_step():
    assert "classify the question" in prompts.SYSTEM_PROMPT_QA


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
    assert "Honesty" in prompts.SYSTEM_PROMPT_PRAVACHAN


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
    assert prompts.get_system_prompt("qa") is prompts.SYSTEM_PROMPT_QA
    assert prompts.get_system_prompt("pravachan") is prompts.SYSTEM_PROMPT_PRAVACHAN
    assert prompts.get_system_prompt("reading") is prompts.SYSTEM_PROMPT_READING


def test_get_system_prompt_raises_for_unknown_mode():
    import pytest
    with pytest.raises(ValueError, match="Unknown mode"):
        prompts.get_system_prompt("bogus")
