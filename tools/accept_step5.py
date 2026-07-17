#!/usr/bin/env python3
"""RFC-017 handover step-5 acceptance harness: boot the FastAPI backend in
process, POST /ask (mode=qa) under `ENABLE_SMALL_TO_BIG=1` for 3 queries that
should each surface a re-OCR'd Surya book, and verify the LLM's citation body
is clean Devanagari (no mojibake replacement chars) sourced from the target
work.

Usage:
    ANTHROPIC_API_KEY=sk-... /Users/neharepal/gurudev-corpus/.venv/bin/python \
        tools/accept_step5.py

Exits 0 on all-pass, 1 on any miss (no clean cite from a target work).
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# Backend requires the API key at startup — fail loud, not obscure.
if not os.environ.get("ANTHROPIC_API_KEY"):
    print("ERROR: ANTHROPIC_API_KEY not set. Export it before running.",
          file=sys.stderr)
    sys.exit(2)

# Flag on for the run — must be set before _retrieve reads it.
os.environ["ENABLE_SMALL_TO_BIG"] = "1"
# Explicitly OFF: no re-generation on grounding-check fail (cost control —
# each /ask should cost exactly one Sonnet 4.6 call).
os.environ.pop("GROUNDING_MODE", None)

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

from fastapi.testclient import TestClient  # noqa: E402
import server as server_mod  # noqa: E402


# Wrap Anthropic client.messages.create to capture per-call usage so we can
# report the actual spend rather than guess.
USAGE_LOG: list[dict] = []


def _install_usage_capture() -> None:
    client = server_mod.STATE.client.client  # anthropic.Anthropic()
    orig_create = client.messages.create

    def wrapped_create(*args, **kwargs):
        resp = orig_create(*args, **kwargs)
        u = getattr(resp, "usage", None)
        if u is not None:
            USAGE_LOG.append({
                "model": kwargs.get("model") or getattr(resp, "model", "?"),
                "input": getattr(u, "input_tokens", 0) or 0,
                "output": getattr(u, "output_tokens", 0) or 0,
                "cache_creation": getattr(u, "cache_creation_input_tokens", 0) or 0,
                "cache_read": getattr(u, "cache_read_input_tokens", 0) or 0,
            })
        return resp

    client.messages.create = wrapped_create


# Anthropic per-Mtok prices (USD) at time of writing. Cache reads are ~1/10 of
# base input; cache-creation writes are ~1.25× base input.
_PRICES = {
    "claude-sonnet-4-6":       {"in": 3.00, "out": 15.00},
    "claude-opus-4-7":         {"in": 15.0, "out": 75.00},
    "claude-haiku-4-5":        {"in": 1.00, "out": 5.00},
    "claude-haiku-4-5-20251001": {"in": 1.00, "out": 5.00},
}


def _estimate_cost() -> tuple[float, list[dict]]:
    per_call = []
    total = 0.0
    for u in USAGE_LOG:
        p = _PRICES.get(u["model"]) or {"in": 3.00, "out": 15.00}
        in_usd = u["input"] * p["in"] / 1_000_000
        cr_usd = u["cache_read"] * (p["in"] * 0.10) / 1_000_000
        cw_usd = u["cache_creation"] * (p["in"] * 1.25) / 1_000_000
        out_usd = u["output"] * p["out"] / 1_000_000
        call = in_usd + cr_usd + cw_usd + out_usd
        total += call
        per_call.append({**u, "call_usd": round(call, 4)})
    return total, per_call


# The 3 target queries — one per re-OCR'd Surya book. Each targets Devanagari
# content that only surfaces if retrieval reaches the book AND the answer
# model quotes it as a citation body.
CASES = [
    {
        # Q1 rewritten: use a distinctive name that appears in sonari-pane-2000
        # ("शिवलिंगव्वक्का" surfaces in sonari-pane-2000--mr--0002--002 alongside
        # the lineage names). The earlier "Amburao Maharaj + disciples" phrasing
        # matched other sampradaya works more strongly.
        "work_id": "sonari-pane-2000",
        "query": "शिवलिंगव्वक्का यांच्याबद्दल गुरुदेव रानडे आणि निंबरगी संप्रदायातील साधकांची आठवण काय होती?",
        "lang": "mr",
    },
    {
        "work_id": "gurudev-paramarthik-shikvan",
        "query": "काकासाहेब तुळपुळे यांनी गुरुदेव रानडे यांच्या पारमार्थिक शिकवणीचे कसे वर्णन केले आहे?",
        "lang": "mr",
    },
    {
        "work_id": "javak-patre-tipane",
        "query": "श्रीभाऊसाहेब महाराज उमदीकर यांच्या जावक पत्रांमधून काय शिकवण मिळते?",
        "lang": "mr",
    },
]

# Mojibake / control-character sentinels. Surya output should not contain any.
_REPLACEMENT_CHAR = "�"
_ZWSP_BOM = ("​", "﻿")


def _cite_is_clean(body: str) -> tuple[bool, str]:
    if not body:
        return False, "empty body"
    if _REPLACEMENT_CHAR in body:
        return False, f"contains U+FFFD"
    for cp in _ZWSP_BOM:
        if cp in body:
            return False, f"contains {hex(ord(cp))}"
    # Devanagari ratio must be substantial (target books are Marathi).
    deva = len(re.findall(r"[ऀ-ॿ]", body))
    if deva < 20:
        return False, f"too little Devanagari ({deva} chars)"
    ascii_letters = len(re.findall(r"[A-Za-z]", body))
    if ascii_letters > deva:
        return False, f"more Latin than Devanagari ({ascii_letters} vs {deva})"
    return True, f"clean: {deva} Devanagari chars"


def run_case(client: TestClient, case: dict) -> dict:
    r = client.post("/ask", json={
        "question": case["query"],
        "mode": "qa",
        "lang": case["lang"],
    }, headers={"accept": "application/json"})
    if r.status_code != 200:
        return {"case": case, "verdict": "HTTP_ERROR",
                "detail": f"{r.status_code} {r.text[:400]}"}
    data = r.json()
    cits = data.get("citations") or []
    if not cits:
        return {"case": case, "verdict": "NO_CITATIONS", "cits": []}

    matches = []
    for c in cits:
        q = c.get("quote") or {}
        wid = q.get("workId") or ""
        body = q.get("body") or ""
        clean, why = _cite_is_clean(body)
        matches.append({
            "workId": wid,
            "workTitle": q.get("workTitle", ""),
            "body_head": body[:120],
            "body_len": len(body),
            "clean": clean,
            "clean_reason": why,
            "readPage": q.get("readPage"),
        })

    hit = [m for m in matches if m["workId"] == case["work_id"] and m["clean"]]
    return {
        "case": case,
        "verdict": "PASS" if hit else "MISS",
        "cits": matches,
    }


def main() -> int:
    # Optional CLI filter: `--only 1,3` skips Q2 to keep cost down when
    # re-investigating specific cases.
    only = None
    if "--only" in sys.argv:
        i = sys.argv.index("--only")
        only = {int(x) for x in sys.argv[i + 1].split(",") if x.strip()}

    cases = [(i, c) for i, c in enumerate(CASES, 1) if only is None or i in only]

    print(f"[step5] booting server in-process (this loads corpus + BGE-M3)...",
          flush=True)
    with TestClient(server_mod.app) as client:
        _install_usage_capture()
        print(f"[step5] server ready. ENABLE_SMALL_TO_BIG=1, "
              f"model={server_mod.STATE.__dict__.get('model_name','?')}"
              f"{' (running only ' + str(sorted(only)) + ')' if only else ''}",
              flush=True)
        results = []
        for i, case in cases:
            print(f"\n[step5] {i}/{len(CASES)}  target={case['work_id']}",
                  flush=True)
            print(f"        query: {case['query'][:90]}...", flush=True)
            r = run_case(client, case)
            results.append(r)
            print(f"        VERDICT: {r['verdict']}", flush=True)
            if r.get("detail"):
                print(f"        DETAIL: {r['detail'][:500]}", flush=True)
            for m in r.get("cits", [])[:5]:
                mark = "OK " if m["clean"] else "!! "
                print(f"          {mark}[{m['workId']}] "
                      f"page={m['readPage']!r} len={m['body_len']}  "
                      f"{m['clean_reason']}", flush=True)
                print(f"              body: {m['body_head']!r}", flush=True)

    print("\n" + "=" * 68)
    n_pass = sum(1 for r in results if r["verdict"] == "PASS")
    print(f"step-5 acceptance: {n_pass}/{len(results)} PASS", flush=True)

    total, per_call = _estimate_cost()
    print(f"\n[step5] LLM spend across {len(per_call)} calls:")
    for i, c in enumerate(per_call, 1):
        print(f"  #{i}  model={c['model']}  "
              f"in={c['input']} out={c['output']} "
              f"cache_read={c['cache_read']} cache_creation={c['cache_creation']} "
              f"→ ${c['call_usd']:.4f}")
    print(f"[step5] estimated total: ${total:.4f} USD")
    return 0 if n_pass == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
