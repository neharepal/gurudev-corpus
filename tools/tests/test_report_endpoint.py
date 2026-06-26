"""Tests for the POST /report endpoint.

Uses FastAPI's TestClient with the startup hook bypassed (same pattern as
test_read_endpoint.py and test_works_endpoint.py) — no embeddings, no API key.

The test monkeypatches `server.ISSUE_QUEUE_PATH` to a tmp file so the real
logs/issue_reports.jsonl is never touched.
"""

import json
import os
import sys
from pathlib import Path

import pytest

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
    """Redirect the queue file to a temp path for each test."""
    import server

    queue_file = tmp_path / "issue_reports.jsonl"
    monkeypatch.setattr(server, "ISSUE_QUEUE_PATH", queue_file)
    return queue_file


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


def test_report_appends_jsonl_line(client, tmp_queue):
    payload = {
        "question": "नामसाधनेविषयी काय सांगतात?",
        "mode": "pravachan",
        "citations": [
            {"workTitle": "Mysticism in Maharashtra", "location": "Ch. 3"},
            {"workTitle": "Pathway to God", "location": "p. 45"},
        ],
        "note": "Second citation has garbled Devanagari.",
    }
    resp = client.post("/report", json=payload)
    assert resp.status_code == 200

    assert tmp_queue.exists(), "Queue file must be created after a report"
    lines = [l for l in tmp_queue.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 1, f"Expected 1 JSON line, got {len(lines)}"

    record = json.loads(lines[0])
    assert record["question"] == payload["question"]
    assert record["mode"] == payload["mode"]
    assert len(record["citations"]) == 2
    assert record["citations"][0]["workTitle"] == "Mysticism in Maharashtra"
    assert record["citations"][1]["location"] == "p. 45"
    assert record["note"] == "Second citation has garbled Devanagari."
    # Timestamp must be present and parseable as ISO-8601
    assert "timestamp" in record
    from datetime import datetime, timezone
    ts = datetime.fromisoformat(record["timestamp"])
    assert ts.tzinfo is not None, "Timestamp must be timezone-aware (UTC)"


def test_report_appends_multiple_lines(client, tmp_queue):
    for i in range(3):
        resp = client.post(
            "/report",
            json={"question": f"Q{i}", "mode": "qa"},
        )
        assert resp.status_code == 200

    lines = [l for l in tmp_queue.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 3, f"Expected 3 JSON lines, got {len(lines)}"
    for line in lines:
        json.loads(line)  # each line must be valid JSON


def test_report_optional_fields_absent(client, tmp_queue):
    """citations and note are optional — omitting them must succeed."""
    resp = client.post(
        "/report",
        json={"question": "Who was Gurudev?", "mode": "qa"},
    )
    assert resp.status_code == 200

    lines = [l for l in tmp_queue.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["citations"] == []
    assert record["note"] == ""


def test_report_missing_required_field_returns_422(client, tmp_queue):
    """question is required — omitting it must return 422."""
    resp = client.post("/report", json={"mode": "qa"})
    assert resp.status_code == 422


def test_report_correction_appends_correct_fields(client, tmp_queue):
    """A correction-shaped body is appended with kind, slug, paragraph, original, corrected."""
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

    lines = [l for l in tmp_queue.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["kind"] == "correction"
    assert record["slug"] == "pathway-to-god-in-hindi-literature"
    assert record["page"] == 3
    assert record["paragraph"] == 12
    assert record["original"] == "गरबल्ड txt हेरे"
    assert record["corrected"] == "गार्बल्ड मजकूर येथे"
    assert record["lang"] == "mr"
    # Timestamp must be present and UTC
    from datetime import datetime
    ts = datetime.fromisoformat(record["timestamp"])
    assert ts.tzinfo is not None
