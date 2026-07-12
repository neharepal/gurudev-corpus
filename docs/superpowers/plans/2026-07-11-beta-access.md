# Beta Access Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Open Gurudev Sangrah to a trusted handful of async beta testers via a tunnel from the operator's Mac, with a password+name gate, per-person + global daily API-spend caps, and query/feedback logging.

**Architecture:** Additions only — no migration. Backend (FastAPI, `tools/server.py`) gains cap-checking, query logging, and a `/feedback` endpoint. Frontend (Next.js, `chat-app/`) gains a password gate, a name prompt, a per-question `client_qid`, and 👍/👎 feedback. A Cloudflare Tunnel exposes the Next.js frontend; the backend stays private behind it.

**Tech Stack:** Python 3.8 + FastAPI + pydantic (backend); Next.js/React/TypeScript (frontend); `cloudflared` (tunnel); pytest (backend tests).

## Global Constraints

- Python interpreter: `/Users/neharepal/opt/anaconda3/bin/python` (has fastapi, pydantic, pytest).
- Run all Python/shell that touches Devanagari under `LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8`.
- All new log/state files live under `logs/` (already gitignored): `logs/beta_queries.jsonl`, `logs/beta_feedback.jsonl`, `logs/beta_usage.json`.
- Caps are tunable module constants: `PER_PERSON_PER_DAY = 15`, `TOTAL_PER_DAY = 100`.
- Identity header: `X-Beta-User` (the tester's self-entered name). Per-question id field: `client_qid` (uuid string the frontend generates).
- Backend tests use `fastapi.testclient.TestClient`. Do NOT make real Anthropic calls in tests — cap-rejection paths return before any LLM call, and that's what the tests exercise.
- Existing test suite (`pytest tools/tests`) is green at 283; keep it green.

---

### Task 1: Daily cap logic (`beta_limits.py`)

**Files:**
- Create: `tools/beta_limits.py`
- Test: `tools/tests/test_beta_limits.py`

**Interfaces:**
- Produces: `class DailyLimiter(path: Path, per_person: int, total: int, today_fn=...)`; method `check_and_count(user: str) -> tuple[bool, str]` returns `(allowed, reason)` where `reason` is `""`, `"per_person"`, or `"global"`. Persists to `path` as JSON `{"date": "YYYY-MM-DD", "global": int, "per_user": {name: int}}`; resets when `today_fn()` differs from stored date. `today_fn` defaults to `lambda: datetime.date.today().isoformat()` and is injectable for tests.

- [ ] **Step 1: Write the failing test**

```python
# tools/tests/test_beta_limits.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from beta_limits import DailyLimiter


def _lim(tmp_path, day="2026-07-11", per=2, total=3):
    box = {"d": day}
    return DailyLimiter(tmp_path / "usage.json", per_person=per, total=total,
                        today_fn=lambda: box["d"]), box


def test_allows_under_caps(tmp_path):
    lim, _ = _lim(tmp_path)
    assert lim.check_and_count("ramesh") == (True, "")
    assert lim.check_and_count("ramesh") == (True, "")


def test_per_person_cap_blocks_third(tmp_path):
    lim, _ = _lim(tmp_path, per=2)
    lim.check_and_count("ramesh"); lim.check_and_count("ramesh")
    assert lim.check_and_count("ramesh") == (False, "per_person")
    # a different person is still allowed (until the global cap)
    assert lim.check_and_count("sunita") == (True, "")


def test_global_cap_blocks(tmp_path):
    lim, _ = _lim(tmp_path, per=100, total=2)
    lim.check_and_count("a"); lim.check_and_count("b")
    assert lim.check_and_count("c") == (False, "global")


def test_counts_reset_on_new_day(tmp_path):
    lim, box = _lim(tmp_path, per=1)
    assert lim.check_and_count("ramesh") == (True, "")
    assert lim.check_and_count("ramesh") == (False, "per_person")
    box["d"] = "2026-07-12"
    assert lim.check_and_count("ramesh") == (True, "")


def test_persists_across_instances(tmp_path):
    p = tmp_path / "usage.json"
    a = DailyLimiter(p, per_person=1, total=9, today_fn=lambda: "2026-07-11")
    assert a.check_and_count("ramesh") == (True, "")
    b = DailyLimiter(p, per_person=1, total=9, today_fn=lambda: "2026-07-11")
    assert b.check_and_count("ramesh") == (False, "per_person")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/neharepal/opt/anaconda3/bin/python -m pytest tools/tests/test_beta_limits.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'beta_limits'`.

- [ ] **Step 3: Write minimal implementation**

```python
# tools/beta_limits.py
"""Per-person + global daily request caps for the beta (RFC-015).

Counts are kept in a small JSON file and reset when the local date rolls over.
check_and_count() is the single entry point: it atomically increments and
returns whether the request is allowed. Fail-open on a corrupt state file
(treat as a fresh day) so a bad file never hard-blocks the beta.
"""
from __future__ import annotations
import datetime, json, os
from pathlib import Path
from typing import Callable


def _today() -> str:
    return datetime.date.today().isoformat()


class DailyLimiter:
    def __init__(self, path: Path, *, per_person: int, total: int,
                 today_fn: Callable[[], str] = _today) -> None:
        self.path = Path(path)
        self.per_person = per_person
        self.total = total
        self.today_fn = today_fn

    def _load(self) -> dict:
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(d, dict) or "date" not in d:
                raise ValueError
        except Exception:
            d = {"date": self.today_fn(), "global": 0, "per_user": {}}
        if d.get("date") != self.today_fn():
            d = {"date": self.today_fn(), "global": 0, "per_user": {}}
        d.setdefault("global", 0)
        d.setdefault("per_user", {})
        return d

    def _save(self, d: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(d), encoding="utf-8")
        os.replace(tmp, self.path)

    def check_and_count(self, user: str) -> tuple[bool, str]:
        d = self._load()
        if d["global"] >= self.total:
            return False, "global"
        if d["per_user"].get(user, 0) >= self.per_person:
            return False, "per_person"
        d["global"] += 1
        d["per_user"][user] = d["per_user"].get(user, 0) + 1
        self._save(d)
        return True, ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/neharepal/opt/anaconda3/bin/python -m pytest tools/tests/test_beta_limits.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add tools/beta_limits.py tools/tests/test_beta_limits.py
git commit -m "beta: per-person + global daily cap logic (RFC-015)"
```

---

### Task 2: Query + feedback JSONL logging (`beta_log.py`)

**Files:**
- Create: `tools/beta_log.py`
- Test: `tools/tests/test_beta_log.py`

**Interfaces:**
- Produces: `log_query(path: Path, record: dict) -> None` and `log_feedback(path: Path, record: dict) -> None` — each appends one JSON line (UTF-8, `ensure_ascii=False`), creating the parent dir. `read_jsonl(path: Path) -> list[dict]` reads them back (returns `[]` if absent).

- [ ] **Step 1: Write the failing test**

```python
# tools/tests/test_beta_log.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from beta_log import log_query, log_feedback, read_jsonl


def test_append_and_read(tmp_path):
    p = tmp_path / "q.jsonl"
    log_query(p, {"client_qid": "x1", "user": "रमेश", "question": "भक्ती?"})
    log_query(p, {"client_qid": "x2", "user": "sunita", "question": "bhakti?"})
    rows = read_jsonl(p)
    assert len(rows) == 2
    assert rows[0]["user"] == "रमेश"           # devanagari round-trips
    assert rows[1]["client_qid"] == "x2"


def test_read_missing_file_is_empty(tmp_path):
    assert read_jsonl(tmp_path / "nope.jsonl") == []


def test_feedback_append(tmp_path):
    p = tmp_path / "f.jsonl"
    log_feedback(p, {"client_qid": "x1", "user": "ramesh", "rating": "up"})
    assert read_jsonl(p)[0]["rating"] == "up"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/neharepal/opt/anaconda3/bin/python -m pytest tools/tests/test_beta_log.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'beta_log'`.

- [ ] **Step 3: Write minimal implementation**

```python
# tools/beta_log.py
"""Append-only JSONL logging for beta queries and feedback (RFC-015)."""
from __future__ import annotations
import json
from pathlib import Path


def _append(path: Path, record: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def log_query(path: Path, record: dict) -> None:
    _append(path, record)


def log_feedback(path: Path, record: dict) -> None:
    _append(path, record)


def read_jsonl(path: Path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/neharepal/opt/anaconda3/bin/python -m pytest tools/tests/test_beta_log.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add tools/beta_log.py tools/tests/test_beta_log.py
git commit -m "beta: JSONL query + feedback logging (RFC-015)"
```

---

### Task 3: Wire caps + logging + `/feedback` into the server

**Files:**
- Modify: `tools/server.py` (the `/ask` handler + add a `/feedback` route + module-level limiter/log paths)
- Test: `tools/tests/test_beta_server.py`

**Interfaces:**
- Consumes: `DailyLimiter` (Task 1), `log_query`/`log_feedback` (Task 2).
- Produces: `/ask` reads header `X-Beta-User` (default `"anon"`), calls the limiter BEFORE retrieval/LLM, returns HTTP 429 `{"error": "...", "reason": "per_person"|"global"}` when blocked, else logs the query. New route `POST /feedback` with body `{client_qid, user, question, rating, comment?}` → `log_feedback` → `{"ok": true}`.

**Context to read first:** open `tools/server.py`, find the FastAPI `app = FastAPI(...)` and the `@app.post("/ask")` handler and its request model (call it `AskBody`). The beta gating is added at the very top of that handler.

- [ ] **Step 1: Write the failing test**

```python
# tools/tests/test_beta_server.py
import os, sys, importlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

def _client(tmp_path, monkeypatch):
    # point beta state/logs at tmp + tiny caps, then import server fresh
    monkeypatch.setenv("BETA_USAGE_PATH", str(tmp_path / "usage.json"))
    monkeypatch.setenv("BETA_QUERY_LOG", str(tmp_path / "q.jsonl"))
    monkeypatch.setenv("BETA_FEEDBACK_LOG", str(tmp_path / "f.jsonl"))
    monkeypatch.setenv("BETA_PER_PERSON", "1")
    monkeypatch.setenv("BETA_TOTAL", "5")
    import server; importlib.reload(server)
    from fastapi.testclient import TestClient
    return server, TestClient(server.app), tmp_path

def test_feedback_logged(tmp_path, monkeypatch):
    server, c, tp = _client(tmp_path, monkeypatch)
    r = c.post("/feedback", json={"client_qid": "x1", "user": "ramesh",
                                  "question": "q", "rating": "up", "comment": "nice"})
    assert r.status_code == 200 and r.json()["ok"] is True
    from beta_log import read_jsonl
    fb = read_jsonl(tp / "f.jsonl")
    assert fb and fb[0]["rating"] == "up" and fb[0]["client_qid"] == "x1"

def test_per_person_cap_returns_429(tmp_path, monkeypatch):
    server, c, tp = _client(tmp_path, monkeypatch)
    # first request for this user consumes the per-person budget (=1);
    # we only assert the SECOND is blocked at 429 before any LLM call.
    hdr = {"X-Beta-User": "ramesh"}
    body = {"mode": "qa", "question": "test"}
    c.post("/ask", json=body, headers=hdr)          # 1st (may 200 or error later; ignore)
    r2 = c.post("/ask", json=body, headers=hdr)      # 2nd → capped
    assert r2.status_code == 429
    assert r2.json()["reason"] == "per_person"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `LC_ALL=en_US.UTF-8 /Users/neharepal/opt/anaconda3/bin/python -m pytest tools/tests/test_beta_server.py -q`
Expected: FAIL — no `/feedback` route (404) and `/ask` never returns 429.

- [ ] **Step 3: Implement — add near the top of `tools/server.py` (after `app = FastAPI(...)`)**

```python
# --- Beta gating (RFC-015) ---------------------------------------------------
import beta_limits, beta_log
from fastapi import Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel as _BaseModel

_BETA_USAGE = Path(os.environ.get("BETA_USAGE_PATH", str(REPO / "logs" / "beta_usage.json")))
_BETA_QLOG = Path(os.environ.get("BETA_QUERY_LOG", str(REPO / "logs" / "beta_queries.jsonl")))
_BETA_FLOG = Path(os.environ.get("BETA_FEEDBACK_LOG", str(REPO / "logs" / "beta_feedback.jsonl")))
_beta_limiter = beta_limits.DailyLimiter(
    _BETA_USAGE,
    per_person=int(os.environ.get("BETA_PER_PERSON", "15")),
    total=int(os.environ.get("BETA_TOTAL", "100")),
)

_CAP_MSG = {
    "per_person": "You've reached today's question limit for the beta 🙏 — please try again tomorrow.",
    "global":     "The beta has reached today's overall limit 🙏 — please try again tomorrow.",
}

class _FeedbackBody(_BaseModel):
    client_qid: str
    user: str = "anon"
    question: str = ""
    rating: str
    comment: str | None = None

@app.post("/feedback")
def feedback(body: _FeedbackBody):
    beta_log.log_feedback(_BETA_FLOG, body.model_dump())
    return {"ok": True}
```

(`REPO` and `os`/`Path` are already imported in server.py — confirm and reuse; do not re-import.)

- [ ] **Step 4: Implement — gate the top of the `/ask` handler**

Add `x_beta_user: str = Header(default="anon")` to the `/ask` handler signature. As the FIRST lines of the handler body (before any retrieval or LLM call):

```python
    allowed, reason = _beta_limiter.check_and_count(x_beta_user)
    if not allowed:
        return JSONResponse(status_code=429, content={"error": _CAP_MSG[reason], "reason": reason})
```

And immediately after a successful answer is produced (just before returning it in the JSON path), log the query:

```python
    beta_log.log_query(_BETA_QLOG, {
        "client_qid": getattr(body, "client_qid", "") or "",
        "ts": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "user": x_beta_user,
        "question": body.question,
        "mode": body.mode,
        "lang": getattr(body, "lang", None),
        "cited_works": sorted({c.get("workTitle") for c in _cited_dicts} - {None}) if (_cited_dicts := []) else [],
        "n_citations": 0,
    })
```

Note for the implementer: replace the `cited_works`/`n_citations` line with values pulled from the actual response object your handler builds (e.g. `len(result.citations)` and the distinct `workTitle`s). If that's awkward in the streaming path, log the query at request start with just `{client_qid, ts, user, question, mode, lang}` and skip the citation fields — capturing *what was asked* is the priority. Add `client_qid: str | None = None` to the `AskBody` pydantic model so the field is accepted.

- [ ] **Step 5: Run tests**

Run: `LC_ALL=en_US.UTF-8 /Users/neharepal/opt/anaconda3/bin/python -m pytest tools/tests/test_beta_server.py tools/tests -q`
Expected: PASS (new tests pass; existing suite still green).

- [ ] **Step 6: Commit**

```bash
git add tools/server.py tools/tests/test_beta_server.py
git commit -m "beta: gate /ask with daily caps + query logging; add /feedback (RFC-015)"
```

---

### Task 4: Log viewer (`beta_log_view.py`)

**Files:**
- Create: `tools/beta_log_view.py`
- Test: `tools/tests/test_beta_log_view.py`

**Interfaces:**
- Produces: `render(queries: list[dict], feedback: list[dict]) -> str` — a plain-text summary grouped by user, each query line with its 👍/👎 (+comment) joined by `client_qid`. `main()` reads the two default log paths and prints `render(...)`.

- [ ] **Step 1: Write the failing test**

```python
# tools/tests/test_beta_log_view.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from beta_log_view import render

def test_render_joins_feedback():
    q = [{"client_qid": "a", "user": "ramesh", "question": "What is bhakti?"},
         {"client_qid": "b", "user": "ramesh", "question": "Who wrote X?"}]
    f = [{"client_qid": "a", "user": "ramesh", "rating": "up", "comment": "clear"}]
    out = render(q, f)
    assert "ramesh" in out
    assert "What is bhakti?" in out
    assert "👍" in out and "clear" in out
    assert "Who wrote X?" in out          # query with no feedback still shown
```

- [ ] **Step 2: Run test to verify it fails**

Run: `LC_ALL=en_US.UTF-8 /Users/neharepal/opt/anaconda3/bin/python -m pytest tools/tests/test_beta_log_view.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# tools/beta_log_view.py
"""Pretty-print beta queries + feedback, grouped by user (RFC-015)."""
from __future__ import annotations
import sys
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from beta_log import read_jsonl

REPO = Path(__file__).resolve().parent.parent
QLOG = REPO / "logs" / "beta_queries.jsonl"
FLOG = REPO / "logs" / "beta_feedback.jsonl"


def render(queries: list[dict], feedback: list[dict]) -> str:
    fb_by_qid = {f.get("client_qid"): f for f in feedback}
    by_user: dict[str, list[dict]] = defaultdict(list)
    for q in queries:
        by_user[q.get("user", "anon")].append(q)
    lines = []
    for user in sorted(by_user):
        lines.append(f"\n=== {user} ({len(by_user[user])} queries) ===")
        for q in by_user[user]:
            f = fb_by_qid.get(q.get("client_qid"))
            tag = ""
            if f:
                tag = " " + ("👍" if f.get("rating") == "up" else "👎")
                if f.get("comment"):
                    tag += f" «{f['comment']}»"
            lines.append(f"  • {q.get('question','')}{tag}")
    return "\n".join(lines) if lines else "(no queries logged yet)"


def main() -> int:
    print(render(read_jsonl(QLOG), read_jsonl(FLOG)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `LC_ALL=en_US.UTF-8 /Users/neharepal/opt/anaconda3/bin/python -m pytest tools/tests/test_beta_log_view.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/beta_log_view.py tools/tests/test_beta_log_view.py
git commit -m "beta: log viewer joining queries + feedback (RFC-015)"
```

---

### Task 5: Frontend password gate

**Files:**
- Create: `chat-app/app/api/beta-auth/route.ts`
- Create: `chat-app/middleware.ts`
- Create: `chat-app/app/gate/page.tsx`

**Interfaces:**
- Produces: `POST /api/beta-auth` `{password}` → sets httpOnly cookie `gs_beta=ok` (30 days) on match with `process.env.BETA_PASSWORD`, returns `{ok:true}`; 401 otherwise. `middleware.ts` redirects any request without the cookie to `/gate` (allowing `/gate`, `/api/beta-auth`, and static assets).

- [ ] **Step 1: Create the auth route**

```typescript
// chat-app/app/api/beta-auth/route.ts
import { NextResponse } from "next/server";
export const runtime = "nodejs";

export async function POST(req: Request) {
  const { password } = await req.json().catch(() => ({ password: "" }));
  if (!process.env.BETA_PASSWORD || password !== process.env.BETA_PASSWORD) {
    return NextResponse.json({ ok: false }, { status: 401 });
  }
  const res = NextResponse.json({ ok: true });
  res.cookies.set("gs_beta", "ok", {
    httpOnly: true, sameSite: "lax", path: "/",
    maxAge: 60 * 60 * 24 * 30, secure: true,
  });
  return res;
}
```

- [ ] **Step 2: Create the middleware**

```typescript
// chat-app/middleware.ts
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  const open =
    pathname === "/gate" ||
    pathname.startsWith("/api/beta-auth") ||
    pathname.startsWith("/_next") ||
    pathname.startsWith("/favicon") ||
    pathname.startsWith("/public");
  if (open) return NextResponse.next();
  if (req.cookies.get("gs_beta")?.value === "ok") return NextResponse.next();
  const url = req.nextUrl.clone();
  url.pathname = "/gate";
  return NextResponse.redirect(url);
}

export const config = { matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"] };
```

- [ ] **Step 3: Create the gate page**

```tsx
// chat-app/app/gate/page.tsx
"use client";
import { useState } from "react";

export default function Gate() {
  const [pw, setPw] = useState("");
  const [err, setErr] = useState(false);
  const [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr(false);
    const r = await fetch("/api/beta-auth", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: pw }),
    });
    setBusy(false);
    if (r.ok) window.location.href = "/";
    else setErr(true);
  }
  return (
    <main style={{ maxWidth: 360, margin: "18vh auto", padding: 24, textAlign: "center" }}>
      <h1 style={{ fontSize: 20, marginBottom: 8 }}>Gurudev Sangrah — Beta</h1>
      <p style={{ opacity: 0.7, marginBottom: 20 }}>Enter the beta password to continue.</p>
      <form onSubmit={submit}>
        <input type="password" value={pw} onChange={(e) => setPw(e.target.value)}
          placeholder="password" autoFocus
          style={{ width: "100%", padding: 12, fontSize: 16, marginBottom: 12 }} />
        <button disabled={busy || !pw} style={{ width: "100%", padding: 12, fontSize: 16 }}>
          {busy ? "Checking…" : "Enter"}
        </button>
        {err && <p style={{ color: "#b00", marginTop: 12 }}>Incorrect password.</p>}
      </form>
    </main>
  );
}
```

- [ ] **Step 4: Manual test**

Run (in `chat-app/`): `BETA_PASSWORD=testpw npm run dev`, open http://localhost:3000 → should redirect to `/gate`. Wrong password → "Incorrect password." Correct `testpw` → cookie set, redirected to `/`, and the app loads. Reload `/` → stays (cookie persists).

- [ ] **Step 5: Commit**

```bash
git add chat-app/app/api/beta-auth/route.ts chat-app/middleware.ts chat-app/app/gate/page.tsx
git commit -m "beta(frontend): password gate via middleware + cookie (RFC-015)"
```

---

### Task 6: Name capture + `client_qid` + `X-Beta-User` forwarding

**Files:**
- Modify: `chat-app/lib/api.ts` (client `askApi`)
- Modify: `chat-app/app/api/ask/route.ts` (proxy)
- Modify: `chat-app/app/chat/page.tsx` (name prompt on first visit)

**Interfaces:**
- Consumes: backend `X-Beta-User` header + `client_qid` body field (Task 3).
- Produces: every `/api/ask` call carries `X-Beta-User: <name>` and a fresh `client_qid` in the body; `askApi` returns the `client_qid` alongside the response so the feedback UI (Task 7) can use it.

**Context to read first:** open `chat-app/lib/api.ts` and find the `fetch("/api/ask", {...})` call inside `askApi`. Open `chat-app/app/chat/page.tsx` and find where `askApi` is invoked and where you can mount a one-time name prompt.

- [ ] **Step 1: `lib/api.ts` — attach header + qid**

Inside `askApi`, before the `fetch`, add:

```typescript
  const name = (typeof window !== "undefined" && localStorage.getItem("gs_beta_name")) || "anon";
  const clientQid =
    typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : String(Date.now());
```

Add to the fetch `headers`: `"X-Beta-User": name,` and include `client_qid: clientQid` in the JSON body object. Have `askApi` return the qid — e.g. change its resolved value to `{ ...response, clientQid }` (or return a tuple); update the one call site in `chat/page.tsx` accordingly. Keep the existing `AskResponse` typing; add `clientQid: string` to what `askApi` returns.

- [ ] **Step 2: `app/api/ask/route.ts` — forward the header**

In the `fetch(\`${BACKEND_URL}/ask\`, {...})` call, add to `headers`:

```typescript
        "X-Beta-User": req.headers.get("x-beta-user") || "anon",
```

(The `client_qid` rides in the body already since the route spreads `...body`.)

- [ ] **Step 3: `app/chat/page.tsx` — name prompt on first visit**

Near the top of the component, using the existing `usePersistentState` hook:

```tsx
  const [name, setName] = usePersistentState<string>("gs_beta_name", "");
  // one-time prompt if no name yet
  const [draft, setDraft] = useState("");
  if (name === "") {
    return (
      <main style={{ maxWidth: 360, margin: "18vh auto", padding: 24, textAlign: "center" }}>
        <h1 style={{ fontSize: 20, marginBottom: 8 }}>🙏 Welcome</h1>
        <p style={{ opacity: 0.7, marginBottom: 20 }}>What may we call you? (shown only to the app maintainer)</p>
        <input value={draft} onChange={(e) => setDraft(e.target.value)} autoFocus placeholder="your name"
          style={{ width: "100%", padding: 12, fontSize: 16, marginBottom: 12 }} />
        <button disabled={!draft.trim()} onClick={() => setName(draft.trim())}
          style={{ width: "100%", padding: 12, fontSize: 16 }}>Start</button>
      </main>
    );
  }
```

Note: `usePersistentState` stores under `gs_beta_name`, the same key `lib/api.ts` reads. Import `usePersistentState` from `../../hooks/usePersistentState` and `useState` from `react`.

- [ ] **Step 4: Manual test**

`BETA_PASSWORD=testpw npm run dev` (backend also running). Pass the gate → first load of `/chat` shows the name prompt → enter "Ramesh" → chat loads. Ask a question; in a terminal `tail -n1 logs/beta_queries.jsonl` shows `"user":"Ramesh"` and a `client_qid`. Reload → no name prompt (persisted).

- [ ] **Step 5: Commit**

```bash
git add chat-app/lib/api.ts chat-app/app/api/ask/route.ts chat-app/app/chat/page.tsx
git commit -m "beta(frontend): name prompt + client_qid + X-Beta-User forwarding (RFC-015)"
```

---

### Task 7: Feedback UI + proxy

**Files:**
- Create: `chat-app/components/FeedbackButtons.tsx`
- Create: `chat-app/app/api/feedback/route.ts`
- Modify: the answer render in `chat-app/app/chat/page.tsx` (mount `<FeedbackButtons>` under each answer)

**Interfaces:**
- Consumes: backend `POST /feedback` (Task 3); the `clientQid` from `askApi` (Task 6).
- Produces: `<FeedbackButtons clientQid={string} question={string} />` posting `{client_qid, user, question, rating, comment}` to `/api/feedback`.

- [ ] **Step 1: Create the feedback proxy**

```typescript
// chat-app/app/api/feedback/route.ts
import { NextResponse } from "next/server";
export const runtime = "nodejs";
const BACKEND_URL = process.env.GURUDEV_BACKEND_URL || "http://localhost:8765";

export async function POST(req: Request) {
  const body = await req.json().catch(() => null);
  if (!body) return NextResponse.json({ error: "bad json" }, { status: 400 });
  const withUser = { ...body, user: req.headers.get("x-beta-user") || body.user || "anon" };
  try {
    const up = await fetch(`${BACKEND_URL}/feedback`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(withUser),
    });
    return NextResponse.json(await up.json(), { status: up.status });
  } catch {
    return NextResponse.json({ error: "backend unreachable" }, { status: 502 });
  }
}
```

- [ ] **Step 2: Create the component**

```tsx
// chat-app/components/FeedbackButtons.tsx
"use client";
import { useState } from "react";

export function FeedbackButtons({ clientQid, question }: { clientQid: string; question: string }) {
  const [sent, setSent] = useState<null | "up" | "down">(null);
  const [comment, setComment] = useState("");
  const [showComment, setShowComment] = useState(false);

  async function send(rating: "up" | "down") {
    setSent(rating);
    setShowComment(true);
    const name = (typeof window !== "undefined" && localStorage.getItem("gs_beta_name")) || "anon";
    await fetch("/api/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Beta-User": name },
      body: JSON.stringify({ client_qid: clientQid, question, rating, comment: "" }),
    }).catch(() => {});
  }
  async function sendComment() {
    const name = (typeof window !== "undefined" && localStorage.getItem("gs_beta_name")) || "anon";
    await fetch("/api/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Beta-User": name },
      body: JSON.stringify({ client_qid: clientQid, question, rating: sent, comment }),
    }).catch(() => {});
    setShowComment(false);
  }

  return (
    <div style={{ marginTop: 12, display: "flex", gap: 8, alignItems: "center", opacity: 0.85 }}>
      <span style={{ fontSize: 13 }}>Helpful?</span>
      <button aria-label="thumbs up" onClick={() => send("up")}
        style={{ fontWeight: sent === "up" ? 700 : 400 }}>👍</button>
      <button aria-label="thumbs down" onClick={() => send("down")}
        style={{ fontWeight: sent === "down" ? 700 : 400 }}>👎</button>
      {showComment && (
        <>
          <input value={comment} onChange={(e) => setComment(e.target.value)}
            placeholder="one line (optional)" style={{ fontSize: 13, padding: 6, flex: 1 }} />
          <button onClick={sendComment} style={{ fontSize: 13 }}>Send</button>
        </>
      )}
      {sent && !showComment && <span style={{ fontSize: 13 }}>🙏 thanks</span>}
    </div>
  );
}
```

- [ ] **Step 3: Mount it under each answer**

In `chat-app/app/chat/page.tsx`, where an answer is rendered, add below the answer body (using the `clientQid` returned by `askApi` for that turn and the turn's question text):

```tsx
<FeedbackButtons clientQid={turn.clientQid} question={turn.question} />
```

Import: `import { FeedbackButtons } from "../../components/FeedbackButtons";`. Note: store the `clientQid` on each answered turn's state object when `askApi` resolves (Task 6 returns it).

- [ ] **Step 4: Manual test**

Ask a question, click 👍 → a comment box appears; type "clear" → Send. In a terminal: `LC_ALL=en_US.UTF-8 /Users/neharepal/opt/anaconda3/bin/python tools/beta_log_view.py` → shows the query with `👍 «clear»` under the right user.

- [ ] **Step 5: Commit**

```bash
git add chat-app/components/FeedbackButtons.tsx chat-app/app/api/feedback/route.ts chat-app/app/chat/page.tsx
git commit -m "beta(frontend): per-answer 👍/👎 + comment feedback (RFC-015)"
```

---

### Task 8: Launch script + tunnel

**Files:**
- Create: `start_beta.sh` (repo root)
- Modify: `docs/rfc/RFC-015-beta-access.md` (append a "Running the beta" operator section)

**Interfaces:** none (ops).

- [ ] **Step 1: Install cloudflared (one-time, operator)**

Run: `brew install cloudflared` (macOS). Verify: `cloudflared --version`.

- [ ] **Step 2: Create `start_beta.sh`**

```bash
#!/usr/bin/env bash
# Launch the Gurudev Sangrah beta: keeps the Mac awake, starts backend + frontend,
# and opens a Cloudflare tunnel to the frontend. Ctrl-C stops everything.
set -euo pipefail
export LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
: "${ANTHROPIC_API_KEY:?set ANTHROPIC_API_KEY}"
: "${BETA_PASSWORD:?set BETA_PASSWORD}"
REPO="$(cd "$(dirname "$0")" && pwd)"
PY=/Users/neharepal/opt/anaconda3/bin/python

caffeinate -dimsu &                                  # keep Mac awake
CAFF=$!
GURUDEV_BACKEND_PORT=8765 ENABLE_JUNK_WEIGHT=1 GROUNDING_MODE=enforce \
  "$PY" "$REPO/tools/server.py" > "$REPO/logs/server.log" 2>&1 &
BACK=$!
( cd "$REPO/chat-app" && BETA_PASSWORD="$BETA_PASSWORD" npm run start ) > "$REPO/logs/frontend.log" 2>&1 &
FRONT=$!
sleep 8
echo "Backend pid=$BACK  Frontend pid=$FRONT  (logs in logs/)"
echo "Opening Cloudflare tunnel to http://localhost:3000 …"
trap 'kill $CAFF $BACK $FRONT 2>/dev/null || true' EXIT
cloudflared tunnel --url http://localhost:3000       # prints the public https URL
```

Make executable: `chmod +x start_beta.sh`.

- [ ] **Step 3: Build the frontend once**

Run (in `chat-app/`): `npm run build`. (Task 8 uses `npm run start`, which serves the production build.)

- [ ] **Step 4: Manual test**

`ANTHROPIC_API_KEY=… BETA_PASSWORD=testpw ./start_beta.sh` → prints a `https://<random>.trycloudflare.com` URL. Open it on a phone (off wifi) → gate → password → name → ask a question → answer renders → 👍 works. Ctrl-C → all processes stop.

- [ ] **Step 5: Append operator docs to RFC-015 and commit**

Add a "## Running the beta" section to `docs/rfc/RFC-015-beta-access.md` documenting: `brew install cloudflared`, `npm run build`, setting `ANTHROPIC_API_KEY` + `BETA_PASSWORD`, `./start_beta.sh`, sharing the printed URL + password, watching `tools/beta_log_view.py`, and that the ephemeral `trycloudflare.com` URL changes on each restart (a named tunnel needs a Cloudflare account + domain).

```bash
chmod +x start_beta.sh
git add start_beta.sh docs/rfc/RFC-015-beta-access.md
git commit -m "beta: start_beta.sh (caffeinate + backend + frontend + cloudflared) + operator docs (RFC-015)"
```

---

## Self-review notes

- **Spec coverage:** access gate → Task 5; name/identity → Task 6; per-person + global caps → Task 1 + Task 3; query logging → Task 2 + Task 3; feedback endpoint + UI → Task 3 + Task 7; log viewer → Task 4; tunnel + caffeinate + start script → Task 8; error handling (429 messages, backend-unreachable) → Tasks 3, 6, 7. All RFC-015 sections covered.
- **Linkage refinement vs RFC:** feedback links by a **client-generated `client_qid`** (frontend `crypto.randomUUID()`), sent with both the query and its feedback — avoids threading a server id through the SSE stream. This supersedes the RFC's server-generated-`id` wording; behavior (join query↔feedback) is identical.
- **Cap test caveat:** `test_per_person_cap_returns_429` only asserts the 2nd request is capped at 429 *before* any Anthropic call; it does not assert the 1st request's answer (which would need a live API key). This keeps the suite offline.
- **Deferred (RFC open questions):** logging full answer text; named Cloudflare domain; tuning 15/100 after day one.
