"""Structured logging setup.

We avoid adding a dedicated logging dependency. Python's ``logging`` module is
enough — we format each record as a single JSON line so that logs are easy to
grep, ship to a log aggregator, or feed into an eval report.

Every module in the cookbook should obtain its logger via :func:`get_logger`
instead of creating its own. That way callers can reroute or silence logs by
calling :func:`setup_logging` once at program start.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any


class JSONFormatter(logging.Formatter):
    """Format every log record as a single JSON line.

    Reserved fields (``time``, ``level``, ``logger``, ``message``) are always
    emitted. Any extra attributes attached via ``logger.info(msg, extra={...})``
    are merged in. Values that can't be JSON-serialized fall back to ``repr``.
    """

    _RESERVED_ATTRS = frozenset(
        {
            "args",
            "asctime",
            "created",
            "exc_info",
            "exc_text",
            "filename",
            "funcName",
            "levelname",
            "levelno",
            "lineno",
            "module",
            "msecs",
            "message",
            "msg",
            "name",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "stack_info",
            "thread",
            "threadName",
            "taskName",
        }
    )

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in self._RESERVED_ATTRS or key.startswith("_"):
                continue
            try:
                json.dumps(value)
                payload[key] = value
            except (TypeError, ValueError):
                payload[key] = repr(value)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


_configured = False


def setup_logging(level: str | int | None = None, *, force: bool = False) -> None:
    """Install the JSON formatter on the root logger.

    Safe to call multiple times. If ``force`` is ``False`` (the default) the
    second call is a no-op so library users don't surprise each other.
    """

    global _configured
    if _configured and not force:
        return

    resolved = level if level is not None else os.environ.get("COOKBOOK_LOG_LEVEL", "INFO")
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JSONFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(resolved)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a logger, ensuring :func:`setup_logging` has been called once."""
    if not _configured:
        setup_logging()
    return logging.getLogger(name)
