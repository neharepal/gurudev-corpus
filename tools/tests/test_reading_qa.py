"""Tests for RFC-023 — Reading-mode Q&A answer format.

Covers three surfaces:
  1. Prompt / tool selection — a `mode: "reading-qa"` request routes to
     SYSTEM_PROMPT_READING_QA + emit_reading_qa_response; default `mode: "qa"`
     still picks the existing QA prompt/tool.
  2. Response schema — ReadingQaResponse validates a minimal reading-qa
     payload (no passageLinks) and a max-3 payload (with links).
  3. RFC-023 cap — the server truncates passageLinks to 3 and logs a warning
     when the LLM emits more.
  4. Regression pin — QAResponse still validates as before (no format field
     regression on the existing QA path).
"""

import logging
import os
import sys

import pytest

TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS_DIR)

import prompts  # noqa: E402
import schemas  # noqa: E402


# ---------------------------------------------------------------------------
# 1. Prompt + tool selection
# ---------------------------------------------------------------------------


def test_reading_qa_prompt_registered():
    """`get_system_prompt("reading-qa", ...)` returns the new prompt."""
    system = prompts.get_system_prompt("reading-qa", lang="en")
    assert "emit_reading_qa_response" in system, (
        "reading-qa prompt must reference its own tool name"
    )
    assert "Do not paraphrase the current page back at the reader" in system, (
        "reading-qa prompt MUST include the explicit 'don't paraphrase the "
        "current page' rule (RFC-023 §Resolved 2026-08-05)"
    )


def test_reading_qa_prompt_forbids_verbatim_quotes():
    """RFC-023: text is synthesis + conclusion; no verbatim quotes."""
    system = prompts.get_system_prompt("reading-qa", lang="en")
    # Must be an explicit rule the model can lean on.
    assert "verbatim" in system.lower(), (
        "reading-qa prompt should explicitly forbid verbatim quotes"
    )


def test_reading_qa_prompt_governs_link_gating():
    """RFC-023: leave passageLinks empty unless the question asks for sources."""
    system = prompts.get_system_prompt("reading-qa", lang="en")
    # These phrases are the trigger list from the RFC — the prompt must
    # name them so the model knows when to populate links.
    for keyword in ("where does he say", "cite that", "source?", "show me"):
        assert keyword in system, f"reading-qa prompt missing link-trigger example: {keyword!r}"


def test_reading_qa_tool_definition():
    """The tool schema matches the RFC-023 shape."""
    tool = schemas.get_tool("reading-qa")
    assert tool["name"] == "emit_reading_qa_response"
    schema = tool["input_schema"]
    assert schema["required"] == ["question", "text"]
    assert "passageLinks" in schema["properties"]
    assert schema["properties"]["passageLinks"]["maxItems"] == 3, (
        "RFC-023 caps passageLinks at 3 in the JSON schema"
    )
    link_item = schema["properties"]["passageLinks"]["items"]
    assert set(link_item["required"]) == {"label", "workSlug", "page"}


def test_qa_prompt_and_tool_unchanged():
    """Regression pin — the existing QA mode still picks its own prompt/tool."""
    system = prompts.get_system_prompt("qa", lang="en")
    assert "emit_qa_response" in system
    assert "emit_reading_qa_response" not in system, (
        "QA prompt must not accidentally reference the reading-qa tool"
    )
    tool = schemas.get_tool("qa")
    assert tool["name"] == "emit_qa_response"
    # Old QA schema still requires framing (it uses framing OR framingParagraphs).
    assert "framing" in tool["input_schema"]["required"]


# ---------------------------------------------------------------------------
# 2. Response schema validation
# ---------------------------------------------------------------------------


def test_reading_qa_response_minimum_shape():
    """Only question + text — no links — is valid and dumps with format field."""
    payload = {
        "question": "what does nama-smaran mean?",
        "text": "Nama-smaran is the continual remembrance of the divine name — the practice Gurudev calls the essence of sadhana.",
    }
    resp = schemas.ReadingQaResponse.model_validate(payload)
    dumped = resp.model_dump(exclude_none=True)
    assert dumped["format"] == "reading-qa"
    assert dumped["question"] == payload["question"]
    assert dumped["text"] == payload["text"]
    assert "passageLinks" not in dumped, (
        "passageLinks should be omitted (not empty) when the LLM emitted none"
    )


def test_reading_qa_response_with_links():
    """Up to 3 links validate; each link keeps label + workSlug + page."""
    payload = {
        "question": "where does Gurudev talk about it?",
        "text": "Gurudev discusses this in several places.",
        "passageLinks": [
            {"label": "where Gurudev discusses nama-smaran", "workSlug": "kakanchi-pravachane", "page": 12},
            {"label": "the same idea in the Pathway series", "workSlug": "pathway-to-god-in-hindi-literature", "page": 47, "workTitle": "Pathway to God in Hindi Literature"},
        ],
    }
    resp = schemas.ReadingQaResponse.model_validate(payload)
    dumped = resp.model_dump(exclude_none=True)
    assert len(dumped["passageLinks"]) == 2
    assert dumped["passageLinks"][0]["workSlug"] == "kakanchi-pravachane"
    assert "workTitle" not in dumped["passageLinks"][0], (
        "workTitle should be omitted when the same-work link doesn't supply it"
    )
    assert dumped["passageLinks"][1]["workTitle"] == "Pathway to God in Hindi Literature"


def test_reading_qa_response_page_must_be_positive():
    """page < 1 fails validation (RFC-023: 1-based reader page)."""
    payload = {
        "question": "q?",
        "text": "t",
        "passageLinks": [
            {"label": "a link", "workSlug": "some-work", "page": 0},
        ],
    }
    with pytest.raises(Exception):
        schemas.ReadingQaResponse.model_validate(payload)


def test_qa_response_still_validates_unchanged():
    """Regression pin — QAResponse still validates with kind='qa' and no format."""
    payload = {
        "question": "what does bhakti mean?",
        "framing": "Here is what the literature says.",
        "citations": [],
    }
    resp = schemas.QAResponse.model_validate(payload)
    dumped = resp.model_dump(exclude_none=True)
    assert dumped["kind"] == "qa", "QA response keeps `kind` discriminator"
    assert "format" not in dumped, "QA response must NOT sprout a `format` field"


# ---------------------------------------------------------------------------
# 3. Server-side truncation (RFC-023 cap: keep first 3, warn)
# ---------------------------------------------------------------------------


def test_truncate_reading_qa_links_no_op_under_cap():
    tool_input = {
        "question": "q?",
        "text": "t",
        "passageLinks": [{"label": "l1", "workSlug": "w", "page": 1}],
    }
    dropped = schemas.truncate_reading_qa_links(tool_input)
    assert dropped == 0
    assert len(tool_input["passageLinks"]) == 1


def test_truncate_reading_qa_links_caps_and_warns(caplog):
    tool_input = {
        "question": "q?",
        "text": "t",
        "passageLinks": [
            {"label": f"link {i}", "workSlug": "w", "page": i + 1}
            for i in range(5)
        ],
    }
    logger = logging.getLogger("reading_qa")
    with caplog.at_level(logging.WARNING, logger="reading_qa"):
        dropped = schemas.truncate_reading_qa_links(tool_input, logger=logger)
    assert dropped == 2
    assert len(tool_input["passageLinks"]) == 3
    # First 3 in order — links 0, 1, 2 survive.
    assert [l["label"] for l in tool_input["passageLinks"]] == ["link 0", "link 1", "link 2"]
    assert any("truncated to 3" in rec.getMessage() for rec in caplog.records), (
        "server MUST log a warning when it drops LLM-emitted overflow links"
    )


def test_truncate_reading_qa_links_missing_field_is_safe():
    """passageLinks absent is fine (RFC-023: optional / empty by default)."""
    tool_input = {"question": "q?", "text": "t"}
    dropped = schemas.truncate_reading_qa_links(tool_input)
    assert dropped == 0
    assert "passageLinks" not in tool_input


# ---------------------------------------------------------------------------
# 4. _prepare_request routing (RFC-023: mode='reading-qa' selects the new
#     prompt + tool without touching the QA path).
# ---------------------------------------------------------------------------


@pytest.fixture
def patch_retrieve_min(monkeypatch):
    """Stub _retrieve so _prepare_request can run without the corpus/model."""
    import server

    def fake_retrieve(question, *, top_k, candidates, mmr_lambda,
                      max_per_source, metadata_filter=None):
        return [{
            "meta": {"work_id": "kakanchi-pravachane", "title": "Kakanchi Pravachane",
                     "kind": "canonical", "language": "en", "char_start": 0},
            "text": "A passage.",
            "cos_score": 0.9, "mmr_score": 0.85,
        }]

    monkeypatch.setattr(server, "_retrieve", fake_retrieve)
    return None


def test_prepare_request_reading_qa_routes_to_new_prompt(patch_retrieve_min):
    """`mode: "reading-qa"` picks SYSTEM_PROMPT_READING_QA."""
    import server

    req = server.AskRequest(
        mode="reading-qa",
        question="what does nama-smaran mean?",
        lang="en",
        work="kakanchi-pravachane",
    )
    mode, user_msg, system_prompt, chunks, _ = server._prepare_request(req)
    assert mode == "reading-qa"
    assert "emit_reading_qa_response" in system_prompt
    # Body of the reading-qa prompt — one of its distinguishing lines.
    assert "Do not paraphrase the current page back at the reader" in system_prompt


def test_prepare_request_qa_default_unchanged(patch_retrieve_min):
    """Regression pin — `mode: "qa"` still picks the existing QA prompt/tool."""
    import server

    req = server.AskRequest(
        mode="qa",
        question="what does bhakti mean?",
        lang="en",
    )
    mode, user_msg, system_prompt, chunks, _ = server._prepare_request(req)
    assert mode == "qa"
    assert "emit_qa_response" in system_prompt
    assert "emit_reading_qa_response" not in system_prompt


def test_prepare_request_reading_qa_applies_work_filter(monkeypatch):
    """Work-scoped reading-qa restricts retrieval to the current book."""
    import server

    captured = {}

    def fake_retrieve(question, *, top_k, candidates, mmr_lambda,
                      max_per_source, metadata_filter=None):
        captured["metadata_filter"] = metadata_filter
        captured["top_k"] = top_k
        captured["max_per_source"] = max_per_source
        return [{
            "meta": {"work_id": "kakanchi-pravachane", "title": "Kakanchi Pravachane",
                     "kind": "canonical", "language": "en", "char_start": 0},
            "text": "A passage.",
            "cos_score": 0.9, "mmr_score": 0.85,
        }]

    monkeypatch.setattr(server, "_retrieve", fake_retrieve)

    req = server.AskRequest(
        mode="reading-qa",
        question="what does nama-smaran mean?",
        work="kakanchi-pravachane",
    )
    server._prepare_request(req)
    assert captured["metadata_filter"] == {"work_id": "kakanchi-pravachane"}
    # Scoped to one work → max_per_source == top_k (same rule as scoped QA).
    assert captured["max_per_source"] == captured["top_k"]


def test_prepare_request_rejects_unknown_mode(patch_retrieve_min):
    """Unknown modes still 400 — reading-qa doesn't accidentally allowlist gibberish."""
    import server
    from fastapi import HTTPException

    req = server.AskRequest(mode="nonsense-mode", question="q")
    with pytest.raises(HTTPException) as excinfo:
        server._prepare_request(req)
    assert excinfo.value.status_code == 400
