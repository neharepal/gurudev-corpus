# Phase 1B — Grounding (Enforcement + Verification) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the "confident answer with zero citations" failure and flag garbled quotes — on the EXISTING verbatim-splice + tool-use + streaming pipeline, with no Citations API and no frontend change.

**Architecture:** Grounding is added as two orthogonal, flag-gated pieces on the current synthesis path: (1) an **enforcement guard** that regenerates once when a substantive QA answer is under-cited; (2) a **quote verifier** that checks each spliced body against its source chunk and flags mismatches to `flag_queue`. Both fail open (never block an answer). The streaming path, when enforcement is on, buffers the QA answer, enforces, then replays the same SSE events — so the UI contract is unchanged (it loses only the progressive type-out for QA).

**Tech Stack:** Python 3.8, Anthropic SDK (existing `ChatClient`), `rapidfuzz` (fuzzy source match), the existing `schemas.py` splice + `flag_queue.yaml`, pytest.

## Global Constraints

- **No Citations API.** Quotes are already spliced verbatim from source by `schemas.splice_qa_citations`; grounding builds on that.
- Both pieces are **flag-gated** by `GROUNDING_MODE` (`off` = today's behavior; `enforce` = enforcement + verify) and **fail open**: any error yields today's answer.
- **No frontend change.** SSE event shapes (`field`, `array_item`, `done`) are preserved; enforcement buffers then replays them.
- Enforcement is **bounded to ONE retry**; then the answer is surfaced as-is and the event is logged.
- The verifier **never blocks** an answer — it only writes advisory entries to `03_catalog/flag_queue.yaml` (same file/shape the correction flow uses).
- `rapidfuzz` must be import-guarded: if unavailable, the verifier degrades to exact-substring matching only.

## Definitions (used across tasks)

- **Under-cited (QA):** the response has a non-trivial body (framing/framingParagraphs total ≥ 200 chars after strip) AND `len(citations) == 0` AND at least one non-empty passage was supplied to the model (`label_to_chunk` non-empty).
- **Degraded quote:** `schemas.splice_quote_dict` returned `False` for it (unknown passage letter or anchor miss), OR the spliced `body` is not found in the source chunk text by the verifier.

---

### Task 1: `is_under_cited` — pure predicate for the enforcement trigger

**Files:**
- Create: `tools/grounding.py`
- Test: `tools/tests/test_grounding.py`

**Interfaces:**
- Produces: `is_under_cited(response: dict, *, passages_supplied: int) -> bool`.

- [ ] **Step 1: Write the failing test**

```python
# tools/tests/test_grounding.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import grounding as g

_LONG = "x" * 250

def test_substantive_zero_citations_is_under_cited():
    resp = {"framing": _LONG, "citations": []}
    assert g.is_under_cited(resp, passages_supplied=8) is True

def test_has_citations_not_under_cited():
    resp = {"framing": _LONG, "citations": [{"quote": {"body": "..."}}]}
    assert g.is_under_cited(resp, passages_supplied=8) is False

def test_no_passages_supplied_not_under_cited():
    # Nothing to cite -> not a grounding failure (navigational / empty retrieval).
    resp = {"framing": _LONG, "citations": []}
    assert g.is_under_cited(resp, passages_supplied=0) is False

def test_trivial_answer_not_under_cited():
    resp = {"framing": "Not covered in the retrieved passages.", "citations": []}
    assert g.is_under_cited(resp, passages_supplied=8) is False

def test_framing_paragraphs_count_toward_length():
    resp = {"framing": "", "framingParagraphs": ["y" * 130, "z" * 130], "citations": []}
    assert g.is_under_cited(resp, passages_supplied=5) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tools/tests/test_grounding.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'grounding'`

- [ ] **Step 3: Write minimal implementation**

```python
# tools/grounding.py
"""Grounding guards for QA answers: enforcement trigger + quote verification.

Builds on the EXISTING verbatim-splice mechanism (schemas.splice_qa_citations),
NOT the Citations API. See RFC-014 (Grounding decision, amended 2026-07-09).
"""
from __future__ import annotations
from typing import Any

_MIN_SUBSTANTIVE_CHARS = 200


def _body_len(response: dict) -> int:
    fr = (response.get("framing") or "").strip()
    fps = response.get("framingParagraphs") or []
    return len(fr) + sum(len((p or "").strip()) for p in fps)


def is_under_cited(response: dict, *, passages_supplied: int) -> bool:
    """True when a substantive QA answer cites nothing though passages existed.

    Substantive = combined framing/framingParagraphs length >= 200 chars, so a
    short "not covered" note is never flagged. Requires passages_supplied >= 1
    (nothing to cite otherwise). This is the enforcement trigger.
    """
    if passages_supplied < 1:
        return False
    if response.get("citations"):
        return False
    return _body_len(response) >= _MIN_SUBSTANTIVE_CHARS
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tools/tests/test_grounding.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add tools/grounding.py tools/tests/test_grounding.py
git commit -m "grounding: is_under_cited enforcement predicate"
```

---

### Task 2: Enforcement instruction + `enforce_citation` retry wrapper

**Files:**
- Modify: `tools/grounding.py` (add `CITE_HARDER_SUFFIX` + `enforce_qa` orchestration helper).
- Test: `tools/tests/test_grounding_enforce.py`

**Interfaces:**
- Consumes: `is_under_cited` (Task 1).
- Produces: `CITE_HARDER_SUFFIX: str`; `enforce_qa(first: dict, passages_supplied: int, regenerate) -> dict` where `regenerate: Callable[[], dict]` returns a freshly-generated response dict. Returns the better of the two (retried if the first was under-cited AND the retry has citations; else the first). Never raises.

- [ ] **Step 1: Write the failing test**

```python
# tools/tests/test_grounding_enforce.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import grounding as g

_LONG = "x" * 250

def test_retries_when_under_cited_and_takes_cited_retry():
    first = {"framing": _LONG, "citations": []}
    retry = {"framing": _LONG, "citations": [{"quote": {"body": "q"}}]}
    calls = {"n": 0}
    def regen():
        calls["n"] += 1
        return retry
    out = g.enforce_qa(first, passages_supplied=8, regenerate=regen)
    assert out is retry and calls["n"] == 1

def test_no_retry_when_already_cited():
    first = {"framing": _LONG, "citations": [{"quote": {"body": "q"}}]}
    def regen(): raise AssertionError("should not regenerate")
    out = g.enforce_qa(first, passages_supplied=8, regenerate=regen)
    assert out is first

def test_keeps_first_when_retry_still_uncited():
    first = {"framing": _LONG, "citations": []}
    retry = {"framing": _LONG, "citations": []}
    out = g.enforce_qa(first, passages_supplied=8, regenerate=lambda: retry)
    assert out is first  # no improvement -> keep original, don't loop

def test_regen_exception_is_safe():
    first = {"framing": _LONG, "citations": []}
    def regen(): raise RuntimeError("api down")
    out = g.enforce_qa(first, passages_supplied=8, regenerate=regen)
    assert out is first
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tools/tests/test_grounding_enforce.py -q`
Expected: FAIL with `AttributeError: module 'grounding' has no attribute 'enforce_qa'`

- [ ] **Step 3: Write minimal implementation**

Append to `tools/grounding.py`:

```python
CITE_HARDER_SUFFIX = (
    "\n\nIMPORTANT: Your previous attempt made claims without citing any of the "
    "supplied passages. You MUST ground this answer: cite the relevant passages "
    "by reference (passage letter + quoteStart/quoteEnd) for the claims you make. "
    "If a passage touches the topic even partially, quote it rather than "
    "paraphrasing uncited. Do not answer from general knowledge alone."
)


def enforce_qa(first: dict, *, passages_supplied: int, regenerate) -> dict:
    """Return `first`, or a regenerated response if `first` was under-cited.

    One retry only. The retry is accepted only if it actually has citations;
    otherwise the original is kept (never loop, never make it worse). Any
    exception from `regenerate` yields `first`. Caller wires `regenerate` to a
    second LLM call whose system/user prompt carries CITE_HARDER_SUFFIX.
    """
    if not is_under_cited(first, passages_supplied=passages_supplied):
        return first
    try:
        retry = regenerate()
    except Exception:
        return first
    if retry and retry.get("citations"):
        return retry
    return first
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tools/tests/test_grounding_enforce.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add tools/grounding.py tools/tests/test_grounding_enforce.py
git commit -m "grounding: enforce_qa one-shot retry + cite-harder instruction"
```

---

### Task 3: Quote verifier — flag garbled/unmatched cited bodies

**Files:**
- Modify: `tools/grounding.py` (add `verify_citations`).
- Test: `tools/tests/test_grounding_verify.py`

**Interfaces:**
- Consumes: nothing new (operates on the already-spliced citations + `label_to_chunk`).
- Produces: `verify_citations(citations: list, label_to_chunk: dict, *, threshold: int = 85) -> list[dict]` returning one advisory record `{"passage", "workTitle", "score", "reason"}` per citation whose spliced body does not match its source chunk. Pure (no file I/O); the caller writes results to `flag_queue`.

- [ ] **Step 1: Write the failing test**

```python
# tools/tests/test_grounding_verify.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import grounding as g

def _chunk(text): return {"text": text, "meta": {"title": "W", "work_id": "w"}}

def test_clean_quote_passes():
    src = "Bhakti consists in love to God, and through the love of God, in the love of man."
    cits = [{"quote": {"passage": "A", "body": "love to God, and through the love of God"}}]
    flags = g.verify_citations(cits, {"A": _chunk(src)})
    assert flags == []

def test_body_absent_from_source_is_flagged():
    src = "A passage about the Upanishads and self-knowledge."
    cits = [{"quote": {"passage": "A", "body": "he built Carlyle Cottage in 1917"}}]
    flags = g.verify_citations(cits, {"A": _chunk(src)})
    assert len(flags) == 1 and flags[0]["passage"] == "A"

def test_unknown_passage_is_flagged():
    cits = [{"quote": {"passage": "Z", "body": "anything"}}]
    flags = g.verify_citations(cits, {"A": _chunk("...")})
    assert len(flags) == 1 and flags[0]["reason"] == "no source chunk"

def test_empty_body_skipped():
    cits = [{"quote": {"passage": "A", "body": ""}}]
    assert g.verify_citations(cits, {"A": _chunk("text")}) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tools/tests/test_grounding_verify.py -q`
Expected: FAIL with `AttributeError: module 'grounding' has no attribute 'verify_citations'`

- [ ] **Step 3: Write minimal implementation**

Append to `tools/grounding.py`:

```python
import unicodedata

try:
    from rapidfuzz.fuzz import partial_ratio as _partial_ratio
except Exception:  # rapidfuzz optional — degrade to exact substring
    _partial_ratio = None


def _norm(s: str) -> str:
    # NFC-normalize (Devanagari matras) + collapse whitespace for robust matching.
    return " ".join(unicodedata.normalize("NFC", s or "").split())


def _matches(body: str, source: str, threshold: int) -> bool:
    nb, ns = _norm(body), _norm(source)
    if not nb:
        return True  # empty body handled by caller; treat as non-flag
    if nb in ns:
        return True
    if _partial_ratio is None:
        return False
    return _partial_ratio(nb, ns) >= threshold


def verify_citations(citations: list, label_to_chunk: dict, *, threshold: int = 85) -> list:
    """Return advisory flag records for citations whose body ∉ its source chunk.

    A mismatch means the spliced/stored SOURCE is likely OCR-corrupt (the splice
    already forces body from source) — so this feeds source-repair, not answer
    rejection. Never raises; never blocks the answer.
    """
    flags = []
    for c in citations or []:
        q = (c or {}).get("quote") or {}
        body = q.get("body") or ""
        passage = (q.get("passage") or "").strip()
        if not body.strip():
            continue
        chunk = (label_to_chunk or {}).get(passage)
        if chunk is None:
            flags.append({"passage": passage, "workTitle": q.get("workTitle", ""),
                          "score": 0, "reason": "no source chunk"})
            continue
        source = chunk.get("text") or ""
        if not _matches(body, source, threshold):
            score = 0 if _partial_ratio is None else int(_partial_ratio(_norm(body), _norm(source)))
            flags.append({"passage": passage, "workTitle": q.get("workTitle", ""),
                          "score": score, "reason": "body not found in source"})
    return flags
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tools/tests/test_grounding_verify.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add tools/grounding.py tools/tests/test_grounding_verify.py
git commit -m "grounding: verify_citations flags cited bodies missing from source"
```

---

### Task 4: Wire enforcement + verify into the NON-streaming `/ask` path

**Files:**
- Modify: `tools/server.py` — non-streaming branch of `ask()` (~lines 1393–1404), and add a `_append_flags` helper reusing the existing flag-queue writer.
- Test: `tools/tests/test_ask_grounding_nonstream.py`

**Interfaces:**
- Consumes: `grounding.is_under_cited`, `grounding.enforce_qa`, `grounding.verify_citations`, `grounding.CITE_HARDER_SUFFIX`; env `GROUNDING_MODE`.
- Produces: enforced + verified `result` dict from the non-streaming path.

- [ ] **Step 1: Write the failing test**

```python
# tools/tests/test_ask_grounding_nonstream.py
# Exercises _enforce_and_verify_qa: the pure orchestration the handler calls.
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import server

_LONG = "x" * 250

def test_enforce_regenerates_when_uncited(monkeypatch):
    monkeypatch.setenv("GROUNDING_MODE", "enforce")
    first = {"framing": _LONG, "citations": []}
    retry = {"framing": _LONG, "citations": [{"quote": {"passage": "A", "body": "love to God"}}]}
    ltc = {"A": {"text": "love to God and man", "meta": {}}}
    out, flags = server._enforce_and_verify_qa(first, ltc, regenerate=lambda: retry)
    assert out is retry and flags == []

def test_off_mode_is_noop(monkeypatch):
    monkeypatch.delenv("GROUNDING_MODE", raising=False)
    first = {"framing": _LONG, "citations": []}
    out, flags = server._enforce_and_verify_qa(first, {"A": {"text": "t", "meta": {}}},
                                               regenerate=lambda: {"boom": 1})
    assert out is first and flags == []   # no enforcement, no verify when off
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tools/tests/test_ask_grounding_nonstream.py -q`
Expected: FAIL with `AttributeError: module 'server' has no attribute '_enforce_and_verify_qa'`

- [ ] **Step 3: Write minimal implementation**

Add `import grounding` to `tools/server.py`, and a helper:

```python
def _enforce_and_verify_qa(result, label_to_chunk, *, regenerate):
    """Apply the grounding guard to a QA result dict. Returns (result, flags).

    No-op unless GROUNDING_MODE == 'enforce'. `regenerate` produces a second
    QA result dict (already spliced) for the enforcement retry.
    """
    if os.environ.get("GROUNDING_MODE") != "enforce":
        return result, []
    passages = sum(1 for _ in (label_to_chunk or {}))
    result = grounding.enforce_qa(result, passages_supplied=passages, regenerate=regenerate)
    flags = grounding.verify_citations(result.get("citations") or [], label_to_chunk)
    return result, flags
```

Then in the non-streaming branch of `ask()`, after `result = parsed.model_dump(exclude_none=True)` and the existing `_enrich_citations_readpage(...)` for QA, add (QA only):

```python
        def _regen():
            p2, _ = STATE.client.ask_structured(
                mode=mode, system_prompt=system_prompt + grounding.CITE_HARDER_SUFFIX,
                user_message=user_msg, label_to_chunk=label_to_chunk,
            )
            r2 = p2.model_dump(exclude_none=True)
            _enrich_citations_readpage(r2.get("citations") or [], label_to_chunk)
            return r2
        result, _flags = _enforce_and_verify_qa(result, label_to_chunk, regenerate=_regen)
        _append_flags(_flags, req)
```

Add `_append_flags(flags, req)` reusing the existing flag-queue write path (the same YAML `FLAG_QUEUE_PATH` the correction flow appends to; write one entry per flag with `source="auto-verify"`, the question, passage, workTitle, score). Look at the existing correction-append code and mirror its file handling.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tools/tests/test_ask_grounding_nonstream.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add tools/server.py tools/tests/test_ask_grounding_nonstream.py
git commit -m "server: enforcement + verify on non-streaming QA (GROUNDING_MODE=enforce)"
```

---

### Task 5: Enforcement on the STREAMING path (buffer → enforce → replay SSE)

**Files:**
- Modify: `tools/server.py` — streaming branch of `ask()` (`event_stream`, ~lines 1410–1440).
- Test: `tools/tests/test_ask_grounding_stream.py`

**Interfaces:**
- Consumes: `_enforce_and_verify_qa` (Task 4); the existing non-streaming `ask_structured`; `sse`, `_retrieval_event_payload`, `_enrich_citations_readpage`.
- Produces: `_replay_qa_as_sse(result) -> iterator` yielding the same event kinds (`field`, `array_item`, `done`) the true stream emits, from a completed result dict.

**Design note:** When `GROUNDING_MODE == 'enforce'`, the QA streaming path switches to **buffered** generation: generate non-streaming → enforce/verify → replay as SSE. This preserves the SSE event contract (no frontend change) and guarantees grounding, at the cost of the progressive type-out for QA. When `GROUNDING_MODE` is off (default), the current true streaming is used unchanged. This tradeoff is intentional and reversible via the flag (RFC-014).

- [ ] **Step 1: Write the failing test**

```python
# tools/tests/test_ask_grounding_stream.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import server

def test_replay_emits_fields_arrays_and_done():
    result = {
        "kind": "qa", "question": "q", "framing": "F",
        "citations": [{"quote": {"body": "b"}, "whyChosen": "w"}],
        "synthesis": "S",
    }
    events = list(server._replay_qa_as_sse(result))
    kinds = [k for k, _ in events]
    assert kinds[-1] == "done"
    # framing came through as a field, the citation as an array_item
    assert ("field", ) or True  # shape check below
    assert any(k == "field" and p.get("name") == "framing" for k, p in events)
    assert any(k == "array_item" and p.get("array") == "citations" for k, p in events)
    done = [p for k, p in events if k == "done"][0]
    assert done["response"]["synthesis"] == "S"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tools/tests/test_ask_grounding_stream.py -q`
Expected: FAIL with `AttributeError: module 'server' has no attribute '_replay_qa_as_sse'`

- [ ] **Step 3: Write minimal implementation**

Add to `tools/server.py`:

```python
def _replay_qa_as_sse(result):
    """Yield (kind, payload) events equivalent to the live QA stream, from a
    completed result dict. Scalars -> field events; list fields -> array_item
    events; then a final done event. Mirrors ask_structured_stream's shapes so
    the frontend needs no change."""
    for name in ("kind", "classification", "question", "framing", "synthesis"):
        if name in result and result[name] is not None:
            yield "field", {"name": name, "value": result[name]}
    for name in ("framingParagraphs", "citations", "references"):
        items = result.get(name)
        if isinstance(items, list):
            for i, value in enumerate(items):
                yield "array_item", {"array": name, "index": i, "value": value}
            yield "field_close", {"name": name}
    yield "done", {"response": result, "usage": {}}
```

Then in `event_stream()`, branch at the top for QA + enforce:

```python
        if mode == "qa" and os.environ.get("GROUNDING_MODE") == "enforce":
            try:
                parsed, _r = STATE.client.ask_structured(
                    mode=mode, system_prompt=system_prompt,
                    user_message=user_msg, label_to_chunk=label_to_chunk,
                )
                result = parsed.model_dump(exclude_none=True)
                _enrich_citations_readpage(result.get("citations") or [], label_to_chunk)
                def _regen():
                    p2, _ = STATE.client.ask_structured(
                        mode=mode, system_prompt=system_prompt + grounding.CITE_HARDER_SUFFIX,
                        user_message=user_msg, label_to_chunk=label_to_chunk,
                    )
                    r2 = p2.model_dump(exclude_none=True)
                    _enrich_citations_readpage(r2.get("citations") or [], label_to_chunk)
                    return r2
                result, _flags = _enforce_and_verify_qa(result, label_to_chunk, regenerate=_regen)
                _append_flags(_flags, req)
                for kind, payload in _replay_qa_as_sse(result):
                    yield sse(kind, **payload)
                return
            except RuntimeError as e:
                yield sse("error", message=str(e)); return
        # else: existing true-streaming loop unchanged
```

(The `yield sse("retrieval", ...)` line stays first, before this branch.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tools/tests/test_ask_grounding_stream.py tools/tests/test_ask_grounding_nonstream.py -q`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add tools/server.py tools/tests/test_ask_grounding_stream.py
git commit -m "server: buffered enforcement on streaming QA, replay as SSE (no UI change)"
```

---

### Task 6: Grounding eval metric — % of doctrinal answers grounded

**Files:**
- Create: `tools/eval_grounding.py`
- Test: manual run (deliverable is the measurement; API-gated so it is not in CI).

**Interfaces:**
- Consumes: the live server `/ask` (non-streaming JSON) with `GROUNDING_MODE=enforce`.
- Produces: a small labeled set of doctrinal/info questions (incl. the Bhakti case) → reports `% with >=1 citation` and `% with any verify-flag`.

- [ ] **Step 1: Write the harness**

```python
# tools/eval_grounding.py
"""Grounding eval: hit the live server and measure citation coverage.
API-gated (real /ask calls) — run manually, not in CI. Usage:
    ENABLE_RERANK=1 GROUNDING_MODE=enforce python tools/eval_grounding.py
"""
import json, os, sys, urllib.request

PORT = os.environ.get("GURUDEV_BACKEND_PORT", "8765")
QUESTIONS = [
    ("What are Gurudev's views on Bhakti?", "mr"),
    ("गुरुदेव भक्तीविषयी काय सांगतात?", "mr"),
    ("What are the stages of sadhana in Gurudev's teaching?", "en"),
    ("आत्मज्ञानाविषयी गुरुदेव रानडे यांचे विचार काय आहेत?", "mr"),
]

def ask(q, lang):
    body = json.dumps({"mode": "qa", "question": q, "lang": lang}).encode()
    req = urllib.request.Request(f"http://localhost:{PORT}/ask", data=body,
                                 headers={"Content-Type": "application/json",
                                          "Accept": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=120))

def main():
    grounded = 0
    for q, lang in QUESTIONS:
        r = ask(q, lang)
        n = len(r.get("citations") or [])
        grounded += 1 if n >= 1 else 0
        print(f"[{'OK ' if n else 'BARE'}] cites={n:2d}  {q[:50]}")
    print(f"\nGrounded: {grounded}/{len(QUESTIONS)} doctrinal answers have >=1 citation")

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it against the live server**

```bash
# start the server with grounding on, then:
GROUNDING_MODE=enforce python tools/eval_grounding.py
```
Expected: `Grounded: 4/4` — every doctrinal answer has ≥1 citation (the Bhakti case no longer returns a zero-citation essay).

- [ ] **Step 3: Commit**

```bash
git add tools/eval_grounding.py
git commit -m "eval: grounding coverage harness (% doctrinal answers cited)"
```

---

## Final validation (whole plan)

- [ ] Run the grounding test suite:
  `python -m pytest tools/tests/test_grounding.py tools/tests/test_grounding_enforce.py tools/tests/test_grounding_verify.py tools/tests/test_ask_grounding_nonstream.py tools/tests/test_ask_grounding_stream.py -q`
  Expected: all PASS.
- [ ] Restart the server with `GROUNDING_MODE=enforce` (plus Phase 1A flags) and run `python tools/eval_grounding.py` — confirm the Bhakti question returns citations.
- [ ] Spot-check the streaming UI with grounding on: answers still render (events arrive in a burst rather than typing out — expected tradeoff).

## Notes for the implementer

- The verifier writes to `03_catalog/flag_queue.yaml`; reuse the **existing** correction-flow append code (search `server.py` for `FLAG_QUEUE_PATH`) — do not invent a new writer. Mark auto entries `source: "auto-verify"` so they are distinguishable from user corrections.
- `rapidfuzz` may already be installed; if not, `pip install rapidfuzz`. The verifier degrades to exact-substring if it is missing (import-guarded).
- Enforcement doubles LLM cost/latency ONLY when an answer is under-cited (rare) — the common path is a single generation.
- Grounding is orthogonal to Phase 1A retrieval; either can ship first. Recommended: 1A then 1B (retrieval quality first, so the model has better passages to cite).
