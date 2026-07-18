"""RFC-016 §3 light gate + spend backstop + access log.

Three checks, applied to the paid path (`/ask`) and paid-adjacent routes, OFF
by default so local dev stays fast:

    INVITE_CODE  — a shared code sent by the frontend as `X-Invite-Code`
                   header (cookie-driven from the gate page). Missing / wrong
                   code → 401.
    DAILY_ANSWER_CAP — global hard ceiling on answered queries per UTC day.
                       Checked BEFORE the Anthropic call, so overspend costs
                       nothing beyond a friendly 429.

Both env vars unset → gate is a no-op. Set INVITE_CODE alone to gate without
capping; set DAILY_ANSWER_CAP alone to cap without an invite check.

The `/admin/*` routes are intentionally allowlisted here (see
`_UNGATED_PATHS`) so the maintainer can hit them from a plain browser without
needing to send the invite header. The admin surface still lives on the
non-obvious `api.<domain>` subdomain — replace with a real admin-token
header when the sadhak group grows past a trusted handful.

Not a rate-limiter — a first-line "keep the URL from becoming a public toy"
gate. If usage grows past a handful, replace with a real store (Redis) and
per-IP sliding-window limits (RFC-016 §3 open path).
"""
from __future__ import annotations

import datetime
import json
import os
import threading
import time
from pathlib import Path
from typing import Optional

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


# Endpoints that must not be gated — health probes, CORS preflights, and the
# maintainer admin surface (viewed from a plain browser at api.<domain>).
_UNGATED_PATHS = {"/", "/health"}
_UNGATED_PREFIXES = ("/admin/",)
# Only /ask counts against the daily cap (it's the only endpoint that calls
# Anthropic in the paid path). /read and /report stay open behind the invite
# code (they don't spend, but they shouldn't be public either).
_PAID_PATHS = {"/ask"}
# Paths whose activity is worth remembering — the maintainer surfaces this at
# /admin/activity to see who is using the app and what they're asking about.
# /works logs a homepage load ≈ session-start (chat-app fetches it on mount);
# useful proxy for "who logged in when" without a dedicated auth endpoint.
_LOGGED_PATHS = {"/ask", "/report", "/works"}
# Log file (bind-mounted from the host so it survives container restarts).
_ACCESS_LOG_DEFAULT = str(Path(__file__).resolve().parent.parent / "logs" / "access.jsonl")


class _AccessLog:
    """Append-only JSONL log of who is doing what. One line per request; each
    line is a self-contained JSON object so the file can be read/rotated with
    ordinary line tools. Thread-safe writes; failure to write never breaks the
    request path."""

    def __init__(self, path: Optional[str]) -> None:
        self._path = Path(path) if path else None
        self._lock = threading.Lock()
        if self._path is not None:
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
            except OSError:
                self._path = None  # unwritable → silently disable

    @property
    def enabled(self) -> bool:
        return self._path is not None

    def append(self, entry: dict) -> None:
        if self._path is None:
            return
        line = json.dumps(entry, ensure_ascii=False)
        try:
            with self._lock:
                with self._path.open("a", encoding="utf-8") as f:
                    f.write(line + "\n")
        except OSError:
            # Filesystem full, permission changed, etc. — don't crash the app.
            pass

    def tail(self, n: int = 200) -> list[dict]:
        """Return the last `n` entries as parsed dicts, newest last. Used by
        the /admin/activity HTML page. Reads the whole file — fine at
        preview scale; move to a real log store when the file exceeds ~10 MB."""
        if self._path is None or not self._path.exists():
            return []
        try:
            with self._path.open("r", encoding="utf-8") as f:
                lines = f.readlines()
        except OSError:
            return []
        out: list[dict] = []
        for line in lines[-n:]:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out


class _DailyCounter:
    """Thread-safe global count of answered queries, reset at UTC midnight."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._day: Optional[datetime.date] = None
        self._count = 0

    def _today(self) -> datetime.date:
        return datetime.datetime.utcnow().date()

    def try_increment(self, cap: int) -> bool:
        """Return True and increment when under `cap`; False when over."""
        with self._lock:
            today = self._today()
            if self._day != today:
                self._day = today
                self._count = 0
            if self._count >= cap:
                return False
            self._count += 1
            return True

    def snapshot(self) -> tuple[Optional[datetime.date], int]:
        with self._lock:
            return self._day, self._count


class InviteAndCapMiddleware(BaseHTTPMiddleware):
    """Applies invite gate + daily cap to the /ask endpoint.

    Read env once at construction; changing the code / cap needs a
    `docker compose restart backend` (documented in deploy/README.md).
    """

    def __init__(self, app):
        super().__init__(app)
        self.invite_code = os.environ.get("INVITE_CODE", "").strip() or None
        try:
            self.daily_cap = int(os.environ.get("DAILY_ANSWER_CAP", "0"))
        except ValueError:
            self.daily_cap = 0
        self._counter = _DailyCounter() if self.daily_cap > 0 else None
        self.access_log = _AccessLog(
            os.environ.get("ACCESS_LOG_PATH", _ACCESS_LOG_DEFAULT)
        )

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        # OPTIONS (CORS preflight) is never gated — the CORS middleware handles
        # policy; adding auth to preflight breaks browsers.
        if request.method == "OPTIONS" or path in _UNGATED_PATHS:
            return await call_next(request)
        # Admin routes are visited from a plain browser (maintainer's device);
        # the invite-cookie flow is a chat-app concern. Skip the gate here.
        if any(path.startswith(p) for p in _UNGATED_PREFIXES):
            return await call_next(request)

        # Invite code required on every non-preflight, non-health request when
        # INVITE_CODE is set.
        if self.invite_code is not None:
            supplied = request.headers.get("x-invite-code") or ""
            if supplied.strip() != self.invite_code:
                return JSONResponse(
                    {"error": "invite_required"},
                    status_code=401,
                )

        # Daily cap: only /ask counts against the paid budget. Checked BEFORE
        # forwarding — a rejected request costs $0.
        if self._counter is not None and path in _PAID_PATHS:
            if not self._counter.try_increment(self.daily_cap):
                return JSONResponse(
                    {
                        "error": "daily_cap_reached",
                        "detail": (
                            "Today's answer cap has been reached. "
                            "Please try again tomorrow."
                        ),
                    },
                    status_code=429,
                )

        # Peek the JSON body (question / mode / lang / work) for the activity
        # log without disturbing the downstream handler. Standard Starlette
        # pattern: read once, stash on `request._body` so the handler's own
        # `await request.body()` returns the same bytes.
        peeked: dict = {}
        if (self.access_log.enabled
                and request.method in ("POST", "PUT", "PATCH")
                and path in _LOGGED_PATHS):
            try:
                body_bytes = await request.body()
                request._body = body_bytes  # replay for the route handler
                if body_bytes and len(body_bytes) < 200_000:
                    peeked = json.loads(body_bytes)
                    if not isinstance(peeked, dict):
                        peeked = {}
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass
            except Exception:
                pass  # never let logging break the request

        t0 = time.time()
        response = await call_next(request)
        elapsed_ms = int((time.time() - t0) * 1000)

        if self.access_log.enabled and path in _LOGGED_PATHS:
            client = request.client
            entry: dict = {
                "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "name": (request.headers.get("x-sadhak-name") or "").strip()[:80],
                "ip": (client.host if client else "") or "",
                "method": request.method,
                "path": path,
                "status": response.status_code,
                "ms": elapsed_ms,
            }
            # Full detail on /ask so the maintainer can reconstruct any
            # citation query later ("why did it cite that passage?").
            if peeked:
                if "mode" in peeked:
                    entry["mode"] = peeked.get("mode")
                if "lang" in peeked:
                    entry["lang"] = peeked.get("lang")
                if "work" in peeked:
                    entry["work"] = peeked.get("work")
                if "question" in peeked and isinstance(peeked["question"], str):
                    entry["question"] = peeked["question"][:1000]
                # /report specifics
                if "category" in peeked:
                    entry["category"] = peeked.get("category")
                if "note" in peeked and isinstance(peeked["note"], str):
                    entry["note"] = peeked["note"][:500]
            self.access_log.append(entry)

        return response

    def status(self) -> dict:
        """For a future admin dashboard — current cap + today's count."""
        day, count = (self._counter.snapshot()
                       if self._counter is not None else (None, 0))
        return {
            "invite_code_required": self.invite_code is not None,
            "daily_cap": self.daily_cap,
            "today_utc": day.isoformat() if day else None,
            "answered_today": count,
        }
