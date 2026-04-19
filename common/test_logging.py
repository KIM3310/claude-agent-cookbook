"""Tests for :mod:`common.logging`."""

from __future__ import annotations

import io
import json
import logging

from common.logging import JSONFormatter, get_logger, setup_logging


def test_json_formatter_emits_parseable_line() -> None:
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    record.tokens_used = 42
    rendered = formatter.format(record)
    payload = json.loads(rendered)
    assert payload["message"] == "hello"
    assert payload["level"] == "INFO"
    assert payload["tokens_used"] == 42


def test_setup_logging_is_idempotent() -> None:
    setup_logging(force=True)
    setup_logging()  # second call should be a no-op
    logger = get_logger("cookbook.test.idempotent")
    assert logger.isEnabledFor(logging.INFO)


def test_logger_captures_extras_on_root() -> None:
    setup_logging(force=True)
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(JSONFormatter())
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        logger = get_logger("cookbook.test.extras")
        logger.info("ping", extra={"custom": "value"})
        handler.flush()
        lines = [json.loads(line) for line in buf.getvalue().splitlines() if line]
        assert any(entry.get("custom") == "value" for entry in lines)
    finally:
        root.removeHandler(handler)
