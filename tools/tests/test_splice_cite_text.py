"""RFC-017 Task 7: splice quotes the child's `cite_text` when present so an
arthasahit citation copies the verse only (never the sadhak-authored meaning);
retrieval-only children (`retrieval_only=True`) drop the citation entirely.

`chunk["text"]` is the parent section (context the LLM saw). `meta["cite_text"]`
is the child's citable span; splice prefers it and falls through to the parent
when the model quoted something outside the child's span.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import schemas  # noqa: E402


def _chunk(text, meta):
    return {"text": text, "meta": meta}


def test_splice_body_prefers_cite_text_over_parent_text():
    """The parent text carries verse + meaning; splice must anchor on the
    verse-only cite_text so `अर्थ` never appears in a citation body."""
    parent_text = ("करीं धंदा परि आवडती पाय ॥१॥\n"
                   "अर्थ - तुकाराम म्हणतात हे भक्तीचे वर्णन आहे.")
    cite_text = "करीं धंदा परि आवडती पाय"
    label_to_chunk = {
        "A": _chunk(parent_text, {
            "title": "Tukaram Vachanamrut", "author": "tukaram",
            "kind": "canonical", "work_id": "tukaram-vachanamrut",
            "cite_text": cite_text,
        }),
    }
    tool_input = {
        "citations": [{
            "quote": {"passage": "A",
                       "quoteStart": "करीं धंदा",
                       "quoteEnd": "पाय"}
        }]
    }
    schemas.splice_qa_citations(tool_input, label_to_chunk)
    body = tool_input["citations"][0]["quote"]["body"]
    assert "करीं धंदा" in body
    assert "अर्थ" not in body, f"body leaked meaning: {body!r}"
    assert "म्हणतात" not in body, f"body leaked meaning: {body!r}"


def test_splice_full_passage_fallback_uses_cite_text_not_parent():
    """When the anchors miss and the code falls back to the whole passage, the
    fallback body must be the citable `cite_text`, not the parent (which for
    arthasahit contains the sadhak's meaning)."""
    parent_text = ("करीं धंदा परि आवडती पाय ॥१॥\n"
                   "अर्थ - तुकाराम म्हणतात हे भक्तीचे वर्णन आहे.")
    cite_text = "करीं धंदा परि आवडती पाय"
    label_to_chunk = {
        "B": _chunk(parent_text, {
            "title": "Tukaram Vachanamrut", "author": "tukaram",
            "kind": "canonical", "work_id": "tukaram-vachanamrut",
            "cite_text": cite_text,
        }),
    }
    tool_input = {
        "citations": [{
            "quote": {"passage": "B",
                       "quoteStart": "OFF-ANCHOR",
                       "quoteEnd": "MISS"}
        }]
    }
    schemas.splice_qa_citations(tool_input, label_to_chunk)
    body = tool_input["citations"][0]["quote"]["body"]
    assert "अर्थ" not in body, f"fallback leaked meaning: {body!r}"
    assert body.strip() == cite_text.strip()


def test_retrieval_only_child_drops_citation():
    """A child flagged `retrieval_only` (arthasahit uncertain split) must not be
    citable at all — the citation is dropped rather than spliced."""
    parent_text = "unknown verse + meaning blob"
    label_to_chunk = {
        "C": _chunk(parent_text, {
            "title": "Sant Vachanamrut", "author": "sadhak",
            "kind": "canonical", "work_id": "sant-vachanamrut",
            "retrieval_only": True,
        }),
    }
    tool_input = {
        "citations": [{
            "quote": {"passage": "C",
                       "quoteStart": "unknown",
                       "quoteEnd": "blob"}
        }]
    }
    schemas.splice_qa_citations(tool_input, label_to_chunk)
    # Retrieval-only ⇒ citation dropped from the list entirely.
    assert tool_input["citations"] == []


def test_splice_unchanged_when_cite_text_absent():
    """Normal (non-Phase-2) chunks with no cite_text keep the existing behavior:
    splice from the whole chunk text."""
    parent_text = "Bhakti is the supreme means. Nothing else compares."
    label_to_chunk = {
        "D": _chunk(parent_text, {
            "title": "Pathway to God", "author": "ranade",
            "kind": "canonical", "work_id": "pathway-to-god-in-the-vedas",
        }),
    }
    tool_input = {
        "citations": [{
            "quote": {"passage": "D",
                       "quoteStart": "Bhakti is",
                       "quoteEnd": "supreme means"}
        }]
    }
    schemas.splice_qa_citations(tool_input, label_to_chunk)
    body = tool_input["citations"][0]["quote"]["body"]
    assert body.startswith("Bhakti is the supreme means")
