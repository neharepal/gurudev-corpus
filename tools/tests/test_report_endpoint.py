"""Tests for the POST /report endpoint (RFC-004 YAML flag queue).

Uses FastAPI's TestClient with the startup hook bypassed (same pattern as
test_read_endpoint.py and test_works_endpoint.py) — no embeddings, no API key.

The test monkeypatches `server.FLAG_QUEUE_PATH` to a tmp file so the real
03_catalog/flag_queue.yaml is never touched.
"""

import os
import sys
from pathlib import Path

import pytest
import yaml

TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS_DIR)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    """Return a TestClient for the FastAPI app with the startup hook cleared."""
    from fastapi.testclient import TestClient
    import server

    original_handlers = server.app.router.on_startup[:]
    server.app.router.on_startup.clear()
    c = TestClient(server.app, raise_server_exceptions=True)
    server.app.router.on_startup.extend(original_handlers)
    return c


@pytest.fixture()
def tmp_queue(tmp_path, monkeypatch):
    """Redirect the YAML queue file to a temp path for each test."""
    import server

    queue_file = tmp_path / "flag_queue.yaml"
    monkeypatch.setattr(server, "FLAG_QUEUE_PATH", queue_file)
    return queue_file


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_entries(queue_file: Path):
    """Return the list of flag entries from the YAML queue file."""
    raw = yaml.safe_load(queue_file.read_text(encoding="utf-8"))
    assert isinstance(raw, list), f"Expected list at root, got {type(raw)}"
    return raw


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_report_returns_ok(client, tmp_queue):
    payload = {
        "question": "What did Gurudev say about bhakti?",
        "mode": "qa",
        "citations": [{"workTitle": "Pathway to God", "location": "General Introduction"}],
        "note": "The quote body appears garbled — stray characters.",
    }
    resp = client.post("/report", json=payload)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True}


def test_report_appends_yaml_entry(client, tmp_queue):
    payload = {
        "question": "नामसाधनेविषयी काय सांगतात?",
        "mode": "pravachan",
        "citations": [
            {"workTitle": "Mysticism in Maharashtra", "location": "Ch. 3"},
            {"workTitle": "Pathway to God", "location": "p. 45"},
        ],
        "note": "Second citation has garbled Devanagari.",
        "category": "quote-mismatch",
    }
    resp = client.post("/report", json=payload)
    assert resp.status_code == 200

    assert tmp_queue.exists(), "Queue file must be created after a report"
    entries = _load_entries(tmp_queue)
    assert len(entries) == 1, f"Expected 1 entry, got {len(entries)}"

    record = entries[0]
    assert record["question"] == payload["question"]
    assert record["mode"] == payload["mode"]
    assert len(record["citations"]) == 2
    assert record["citations"][0]["workTitle"] == "Mysticism in Maharashtra"
    assert record["citations"][1]["location"] == "p. 45"
    assert record["note"] == "Second citation has garbled Devanagari."
    assert record["category"] == "quote-mismatch"
    # flagged_at must be present and parseable as ISO-8601
    assert "flagged_at" in record
    from datetime import datetime, timezone
    ts = datetime.fromisoformat(record["flagged_at"])
    assert ts.tzinfo is not None, "flagged_at must be timezone-aware (UTC)"


def test_report_category_stored(client, tmp_queue):
    """Category field is stored in the YAML entry."""
    payload = {
        "question": "Who was Gurudev?",
        "mode": "qa",
        "category": "wrong-attribution",
    }
    resp = client.post("/report", json=payload)
    assert resp.status_code == 200

    entries = _load_entries(tmp_queue)
    assert entries[0]["category"] == "wrong-attribution"


def test_report_appends_multiple_entries(client, tmp_queue):
    for i in range(3):
        resp = client.post(
            "/report",
            json={"question": f"Q{i}", "mode": "qa"},
        )
        assert resp.status_code == 200

    entries = _load_entries(tmp_queue)
    assert len(entries) == 3, f"Expected 3 entries, got {len(entries)}"


def test_report_optional_fields_absent(client, tmp_queue):
    """citations, note, and category are optional — omitting them must succeed."""
    resp = client.post(
        "/report",
        json={"question": "Who was Gurudev?", "mode": "qa"},
    )
    assert resp.status_code == 200

    entries = _load_entries(tmp_queue)
    assert len(entries) == 1
    record = entries[0]
    assert record["citations"] == []
    assert record["note"] == ""
    assert record["category"] == ""


def test_report_missing_required_field_returns_422(client, tmp_queue):
    """question is required — omitting it must return 422."""
    resp = client.post("/report", json={"mode": "qa"})
    assert resp.status_code == 422


def test_report_kind_defaults_to_issue(client, tmp_queue):
    """When kind is absent, the stored entry has kind='issue'."""
    resp = client.post(
        "/report",
        json={"question": "Test?", "mode": "qa"},
    )
    assert resp.status_code == 200
    entries = _load_entries(tmp_queue)
    assert entries[0]["kind"] == "issue"


def test_report_correction_appends_correct_fields(client, tmp_queue):
    """A correction-shaped body is appended with kind=correction and correction fields."""
    payload = {
        "question": "",
        "mode": "reading",
        "kind": "correction",
        "slug": "pathway-to-god-in-hindi-literature",
        "page": 3,
        "paragraph": 12,
        "original": "गरबल्ड txt हेरे",
        "corrected": "गार्बल्ड मजकूर येथे",
        "lang": "mr",
    }
    resp = client.post("/report", json=payload)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True}

    entries = _load_entries(tmp_queue)
    assert len(entries) == 1
    record = entries[0]
    assert record["kind"] == "correction"
    assert record["slug"] == "pathway-to-god-in-hindi-literature"
    assert record["page"] == 3
    assert record["paragraph"] == 12
    assert record["original"] == "गरबल्ड txt हेरे"
    assert record["corrected"] == "गार्बल्ड मजकूर येथे"
    assert record["lang"] == "mr"
    # flagged_at must be present and UTC
    from datetime import datetime
    ts = datetime.fromisoformat(record["flagged_at"])
    assert ts.tzinfo is not None


def test_report_yaml_stays_valid_after_multiple_appends(client, tmp_queue):
    """Appending multiple entries keeps the file parseable as a YAML list."""
    for i in range(5):
        client.post("/report", json={"question": f"Q{i}", "mode": "qa", "category": "other"})

    raw = yaml.safe_load(tmp_queue.read_text(encoding="utf-8"))
    assert isinstance(raw, list)
    assert len(raw) == 5
    for entry in raw:
        assert "flagged_at" in entry
        assert entry["category"] == "other"


def test_report_answer_text_persisted(client, tmp_queue):
    """answer_text is stored in the YAML entry when provided."""
    payload = {
        "question": "What did Gurudev say about nāmasādhana?",
        "mode": "qa",
        "category": "quote-mismatch",
        "answer_text": "Gurudev emphasised nāmasādhana as the central practice.\n\nHe wrote extensively about this in Pathway to God.",
    }
    resp = client.post("/report", json=payload)
    assert resp.status_code == 200, resp.text

    entries = _load_entries(tmp_queue)
    assert len(entries) == 1
    record = entries[0]
    assert record["answer_text"] == payload["answer_text"]


def test_report_citations_with_body_persisted(client, tmp_queue):
    """Citations that carry a body field are persisted including the body."""
    payload = {
        "question": "What is the nature of bhakti?",
        "mode": "qa",
        "category": "quote-mismatch",
        "citations": [
            {
                "workTitle": "Pathway to God",
                "location": "General Introduction",
                "body": "The path of devotion leads the aspirant directly to the divine presence.",
            },
            {
                "workTitle": "Mysticism in Maharashtra",
                "location": "Ch. 3",
                # No body — backward-compat: old clients may omit it.
            },
        ],
    }
    resp = client.post("/report", json=payload)
    assert resp.status_code == 200, resp.text

    entries = _load_entries(tmp_queue)
    assert len(entries) == 1
    record = entries[0]
    assert len(record["citations"]) == 2
    # First citation has body.
    first = record["citations"][0]
    assert first["workTitle"] == "Pathway to God"
    assert first["body"] == "The path of devotion leads the aspirant directly to the divine presence."
    # Second citation has no body key (omitted from serialization).
    second = record["citations"][1]
    assert second["workTitle"] == "Mysticism in Maharashtra"
    assert "body" not in second


def test_report_answer_text_absent_when_not_sent(client, tmp_queue):
    """answer_text is NOT present in the entry when the client doesn't send it."""
    resp = client.post(
        "/report",
        json={"question": "Who was Gurudev?", "mode": "qa", "category": "other"},
    )
    assert resp.status_code == 200

    entries = _load_entries(tmp_queue)
    assert len(entries) == 1
    record = entries[0]
    assert "answer_text" not in record


def test_admin_flags_json_returns_answer_text_and_citation_body(client, tmp_queue):
    """GET /admin/flags.json returns answer_text and citation body in the entry."""
    payload = {
        "question": "What is Gurudev's teaching on yoga?",
        "mode": "pravachan",
        "category": "missing-context",
        "answer_text": "Gurudev saw yoga as inner discipline.",
        "citations": [
            {
                "workTitle": "Pathway to God",
                "location": "p. 12",
                "body": "Yoga is the union of the self with the supreme.",
            }
        ],
    }
    resp = client.post("/report", json=payload)
    assert resp.status_code == 200, resp.text

    json_resp = client.get("/admin/flags.json")
    assert json_resp.status_code == 200
    entries = json_resp.json()
    assert isinstance(entries, list)
    assert len(entries) == 1
    record = entries[0]
    assert record["answer_text"] == "Gurudev saw yoga as inner discipline."
    assert record["citations"][0]["body"] == "Yoga is the union of the self with the supreme."
