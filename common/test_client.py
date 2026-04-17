"""Tests for :mod:`common.client`.

These tests run without any network access. They construct a fake SDK object
and inject it via :meth:`CookbookClient.with_raw_client`.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from common.client import (
    CookbookClient,
    UsageLedger,
    _is_transient_error,
    estimate_cost_usd,
)
from common.types import CompletionResult


class _FakeUsage:
    def __init__(self, in_tok: int, out_tok: int, cache_read: int = 0, cache_write: int = 0) -> None:
        self.input_tokens = in_tok
        self.output_tokens = out_tok
        self.cache_read_input_tokens = cache_read
        self.cache_creation_input_tokens = cache_write


class _FakeTextBlock:
    type = "text"

    def __init__(self, text: str) -> None:
        self.text = text


class _FakeResponse:
    def __init__(self, text: str, *, usage: _FakeUsage, stop_reason: str = "end_turn") -> None:
        self.content = [_FakeTextBlock(text)]
        self.usage = usage
        self.stop_reason = stop_reason
        self.model = "claude-sonnet-4-20250514"


def _make_client(responses: list[Any]) -> CookbookClient:
    raw = MagicMock()
    raw.messages.create.side_effect = responses
    return CookbookClient.with_raw_client(raw, default_model="claude-sonnet-4-20250514")


def test_create_message_normalizes_response() -> None:
    client = _make_client([_FakeResponse("hello", usage=_FakeUsage(10, 5))])
    result = client.create_message(messages=[{"role": "user", "content": "hi"}])
    assert isinstance(result, CompletionResult)
    assert result.text == "hello"
    assert result.input_tokens == 10
    assert result.output_tokens == 5
    assert result.stop_reason == "end_turn"


def test_create_message_records_usage_and_cost() -> None:
    client = _make_client([_FakeResponse("ok", usage=_FakeUsage(1000, 500))])
    client.create_message(messages=[{"role": "user", "content": "hi"}])
    summary = client.ledger.summary()
    assert summary["requests"] == 1
    assert summary["input_tokens"] == 1000
    assert summary["output_tokens"] == 500
    # Sonnet rates: 3/mtok input + 15/mtok output = 0.003 + 0.0075 = 0.0105
    assert summary["cost_usd"] == pytest.approx(0.0105, abs=1e-6)


def test_cache_hits_are_not_double_billed() -> None:
    # 900 cached read tokens out of 1000 input — only 100 uncached should be billed.
    usage = _FakeUsage(1000, 500, cache_read=900)
    client = _make_client([_FakeResponse("ok", usage=usage)])
    client.create_message(messages=[{"role": "user", "content": "hi"}])
    summary = client.ledger.summary()
    # 100 uncached * $3/mtok + 500 out * $15/mtok + 900 cache_read * $0.3/mtok
    expected = (100 * 3 + 500 * 15 + 900 * 0.30) / 1_000_000
    assert summary["cost_usd"] == pytest.approx(expected, abs=1e-7)


def test_retries_on_transient_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    class FlakyError(Exception):
        status_code = 503

    ok = _FakeResponse("recovered", usage=_FakeUsage(1, 1))
    raw = MagicMock()
    raw.messages.create.side_effect = [FlakyError("busy"), ok]
    client = CookbookClient.with_raw_client(raw)
    client.max_retries = 2
    # Avoid the real sleep between retries
    import common.client as mod

    monkeypatch.setattr(mod.time, "sleep", lambda _s: None)
    result = client.create_message(messages=[{"role": "user", "content": "hi"}])
    assert result.text == "recovered"
    assert raw.messages.create.call_count == 2


def test_non_transient_errors_are_not_retried() -> None:
    class FatalError(Exception):
        status_code = 400

    raw = MagicMock()
    raw.messages.create.side_effect = FatalError("bad request")
    client = CookbookClient.with_raw_client(raw)
    with pytest.raises(FatalError):
        client.create_message(messages=[{"role": "user", "content": "hi"}])


def test_is_transient_error_classification() -> None:
    class Err(Exception):
        def __init__(self, status: int) -> None:
            self.status_code = status

    assert _is_transient_error(Err(429))
    assert _is_transient_error(Err(503))
    assert not _is_transient_error(Err(400))
    assert not _is_transient_error(Err(404))


def test_estimate_cost_for_unknown_model_falls_back() -> None:
    cost = estimate_cost_usd(
        model="claude-unknown-future",
        input_tokens=1_000_000,
        output_tokens=0,
    )
    assert cost == pytest.approx(3.0)


def test_usage_ledger_accumulates_across_requests() -> None:
    ledger = UsageLedger()
    a = CompletionResult("a", "end_turn", 100, 50)
    b = CompletionResult("b", "end_turn", 200, 25)
    ledger.record(a, model="claude-sonnet-4-20250514")
    ledger.record(b, model="claude-sonnet-4-20250514")
    assert ledger.requests == 2
    assert ledger.input_tokens == 300
    assert ledger.output_tokens == 75
    assert len(ledger.entries) == 2


def test_system_prompt_and_tools_are_forwarded() -> None:
    raw = MagicMock()
    raw.messages.create.return_value = _FakeResponse("ok", usage=_FakeUsage(1, 1))
    client = CookbookClient.with_raw_client(raw)
    client.create_message(
        messages=[{"role": "user", "content": "hi"}],
        system="you are a helpful assistant",
        tools=[{"name": "noop", "description": "", "input_schema": {"type": "object"}}],
        tool_choice={"type": "auto"},
        temperature=0.2,
        extra={"metadata": {"user_id": "u1"}},
    )
    kwargs = raw.messages.create.call_args.kwargs
    assert kwargs["system"] == "you are a helpful assistant"
    assert kwargs["tools"][0]["name"] == "noop"
    assert kwargs["tool_choice"] == {"type": "auto"}
    assert kwargs["temperature"] == 0.2
    assert kwargs["metadata"] == {"user_id": "u1"}
