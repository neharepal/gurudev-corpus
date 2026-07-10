# tools/tests/test_query_understanding_wiring.py
# _extra_query_strings returns the rewrite/HyDE strings to fold into retrieval,
# honoring the env flags; empty when disabled.
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import server

def test_extra_queries_when_enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_QUERY_REWRITE", "1")
    monkeypatch.setenv("ENABLE_HYDE", "1")
    monkeypatch.setattr(server.query_understanding, "rewrite_query", lambda q: "REWRITE")
    monkeypatch.setattr(server.query_understanding, "hypothetical_doc", lambda q: "HYDE")
    assert server._extra_query_strings("q") == ["REWRITE", "HYDE"]

def test_extra_queries_empty_when_disabled(monkeypatch):
    monkeypatch.delenv("ENABLE_QUERY_REWRITE", raising=False)
    monkeypatch.delenv("ENABLE_HYDE", raising=False)
    assert server._extra_query_strings("q") == []
