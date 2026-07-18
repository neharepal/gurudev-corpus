"""Regression: InviteAndCapMiddleware must NOT auto-log a partial entry
when the underlying route returned a StreamingResponse — the streaming
handler owns logging via `_finalize_ask_log`, and double-logging produces
the observed duplicate rows (one partial without answer/retrieved, one
full) with the same microsecond `ts` in access.jsonl.

Historical context (2026-07-18): a `isinstance(response, StreamingResponse)`
check alone was NOT sufficient, because Starlette's `BaseHTTPMiddleware`
re-wraps every response in an internal `_StreamingResponse` class that
does not inherit from `StreamingResponse`. The fix adds a fallback check
on `response.media_type == "text/event-stream"` which the wrapper does
preserve.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

import gate  # noqa: E402


def _make_app(access_log_path: Path) -> FastAPI:
    os.environ["ACCESS_LOG_PATH"] = str(access_log_path)
    os.environ.pop("INVITE_CODE", None)   # no gating, just logging
    os.environ.pop("DAILY_CAP", None)

    app = FastAPI()
    app.add_middleware(gate.InviteAndCapMiddleware)

    @app.post("/ask")
    def ask_streaming():
        def gen():
            # Simulate the /ask handler: mid-stream, write the "full" log
            # entry the way _finalize_ask_log does.
            yield "event: retrieval\ndata: {}\n\n"
            yield "event: done\ndata: {}\n\n"
        return StreamingResponse(gen(), media_type="text/event-stream")

    @app.post("/works")
    def works_json():
        # A non-streaming JSON endpoint — middleware auto-log SHOULD fire here.
        return {"works": []}

    return app


def _read_log_lines(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_streaming_response_does_not_trigger_middleware_autolog(tmp_path):
    """Even under `BaseHTTPMiddleware`'s `_StreamingResponse` wrap, the
    middleware must recognise the SSE response and skip auto-log."""
    log_path = tmp_path / "access.jsonl"
    app = _make_app(log_path)
    client = TestClient(app)
    # Consume the stream so it actually flows through the middleware.
    with client.stream(
        "POST", "/ask",
        headers={"Accept": "text/event-stream"},
    ) as resp:
        assert resp.status_code == 200
        for _ in resp.iter_bytes():
            pass

    entries = _read_log_lines(log_path)
    # The test-app's /ask handler doesn't call _finalize_ask_log, so the
    # LOG SHOULD BE EMPTY — the middleware skipped, the handler didn't write.
    # Before the fix, the middleware would have written a partial entry.
    assert entries == [], (
        f"middleware auto-logged despite streaming response: {entries}"
    )


def test_non_streaming_response_still_triggers_middleware_autolog(tmp_path):
    """Sanity: the fix must NOT accidentally disable logging for regular
    JSON endpoints. /works must still be logged by the middleware."""
    log_path = tmp_path / "access.jsonl"
    app = _make_app(log_path)
    client = TestClient(app)

    resp = client.post("/works")
    assert resp.status_code == 200

    entries = _read_log_lines(log_path)
    assert len(entries) == 1, f"expected exactly one entry, got {entries}"
    assert entries[0].get("path") == "/works"
    assert entries[0].get("status") == 200
