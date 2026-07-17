"""Structured logging seam for the RFC-016 deploy.

Local dev: plain text to stderr (readable). Production: `LOG_JSON=1` in the
env turns on line-per-log JSON records so CloudWatch/Datadog/Loki can parse
without an extra shim. When we migrate off Lightsail to ECS, this is a
zero-code-change flip.

Not opinionated about levels — uvicorn's own access log fires as INFO on the
"uvicorn.access" logger; app code should use `logging.getLogger(__name__)` and
level as appropriate.
"""
from __future__ import annotations

import json
import logging
import os
import sys


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # Attach anything explicitly passed via `extra={...}` on the call site.
        for k, v in record.__dict__.items():
            if k in payload or k.startswith("_"):
                continue
            if k in (
                "name", "msg", "args", "levelname", "levelno", "pathname",
                "filename", "module", "exc_info", "exc_text", "stack_info",
                "lineno", "funcName", "created", "msecs", "relativeCreated",
                "thread", "threadName", "processName", "process", "asctime",
            ):
                continue
            try:
                json.dumps(v)  # only include JSON-serialisable extras
                payload[k] = v
            except TypeError:
                payload[k] = repr(v)
        return json.dumps(payload, ensure_ascii=False)


def configure() -> None:
    """Idempotent — safe to call multiple times."""
    root = logging.getLogger()
    root.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())

    # Remove any handlers uvicorn/uvloop may have attached, then re-add our own.
    for h in list(root.handlers):
        root.removeHandler(h)

    handler = logging.StreamHandler(sys.stdout)
    if os.environ.get("LOG_JSON") == "1":
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-5s %(name)s: %(message)s",
            "%Y-%m-%d %H:%M:%S",
        ))
    root.addHandler(handler)

    # Align uvicorn's loggers to the same handler so access logs share the
    # same format (crucial for log aggregation).
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        for h in list(lg.handlers):
            lg.removeHandler(h)
        lg.propagate = True
