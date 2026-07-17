"""RFC-016 §3 light gate + spend backstop.

Two checks, applied ONLY to the paid path (`/ask`), OFF by default so local dev
stays fast:

    INVITE_CODE  — a shared code sent by the frontend as `X-Invite-Code`
                   header (cookie-driven from the gate page). Missing / wrong
                   code → 401.
    DAILY_ANSWER_CAP — global hard ceiling on answered queries per UTC day.
                       Checked BEFORE the Anthropic call, so overspend costs
                       nothing beyond a friendly 429.

Both env vars unset → gate is a no-op. Set INVITE_CODE alone to gate without
capping; set DAILY_ANSWER_CAP alone to cap without an invite check.

Not a rate-limiter — a first-line "keep the URL from becoming a public toy"
gate. If usage grows past a handful, replace with a real store (Redis) and
per-IP sliding-window limits (RFC-016 §3 open path).
"""
from __future__ import annotations

import datetime
import os
import threading
from typing import Optional

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


# Endpoints that must not be gated — health probes, CORS preflights, and
# static / read routes that don't spend LLM budget.
_UNGATED_PATHS = {"/", "/health"}
# Only /ask counts against the daily cap (it's the only endpoint that calls
# Anthropic in the paid path). /read and /report stay open behind the invite
# code (they don't spend, but they shouldn't be public either).
_PAID_PATHS = {"/ask"}


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

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        # OPTIONS (CORS preflight) is never gated — the CORS middleware handles
        # policy; adding auth to preflight breaks browsers.
        if request.method == "OPTIONS" or path in _UNGATED_PATHS:
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

        return await call_next(request)

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
