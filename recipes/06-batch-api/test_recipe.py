"""Tests for recipe 06."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from common.client import CookbookClient

from .recipe import (
    build_batch_requests,
    iter_batch_results,
    load_batch_jsonl,
    poll_batch,
    run_batch,
    submit_batch,
    write_batch_jsonl,
)


def _client_with_batches(batches_api: Any) -> CookbookClient:
    raw = MagicMock()
    raw.messages = MagicMock()
    raw.messages.batches = batches_api
    return CookbookClient.with_raw_client(raw)


class _FakeBatchRecord:
    def __init__(self, id_: str, status: str) -> None:
        self.id = id_
        self.processing_status = status


class _FakeTextBlock:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _FakeMessage:
    def __init__(self, text: str) -> None:
        self.content = [_FakeTextBlock(text)]


class _FakeResult:
    def __init__(self, text: str, *, type_: str = "succeeded") -> None:
        self.type = type_
        self.message = _FakeMessage(text)


class _FakeResultEntry:
    def __init__(self, custom_id: str, text: str, *, type_: str = "succeeded") -> None:
        self.custom_id = custom_id
        self.result = _FakeResult(text, type_=type_)


def test_build_batch_requests_envelope_shape() -> None:
    reqs = build_batch_requests(
        [("a", "prompt A"), ("b", "prompt B")],
        model="claude-sonnet-4-20250514",
        system="be terse",
        max_tokens=64,
    )
    assert len(reqs) == 2
    assert reqs[0]["custom_id"] == "a"
    assert reqs[0]["params"]["system"] == "be terse"
    assert reqs[0]["params"]["messages"][0]["content"] == "prompt A"
    assert reqs[0]["params"]["max_tokens"] == 64


def test_jsonl_roundtrip(tmp_path: Path) -> None:
    reqs = build_batch_requests([("a", "x")], model="m")
    path = tmp_path / "b.jsonl"
    write_batch_jsonl(reqs, path)
    assert load_batch_jsonl(path) == reqs


def test_submit_batch_returns_id() -> None:
    batches = MagicMock()
    batches.create.return_value = _FakeBatchRecord("msgbatch_01", "in_progress")
    client = _client_with_batches(batches)
    reqs = build_batch_requests([("a", "x")], model="m")
    batch_id = submit_batch(client, reqs)
    assert batch_id == "msgbatch_01"
    batches.create.assert_called_once_with(requests=reqs)


def test_poll_batch_reaches_terminal_state() -> None:
    batches = MagicMock()
    batches.retrieve.side_effect = [
        _FakeBatchRecord("b1", "in_progress"),
        _FakeBatchRecord("b1", "in_progress"),
        _FakeBatchRecord("b1", "ended"),
    ]
    client = _client_with_batches(batches)
    sleeps: list[float] = []
    status, polls = poll_batch(client, "b1", interval_seconds=1.0, sleep=sleeps.append)
    assert status == "ended"
    assert polls == 3
    assert sleeps == [1.0, 1.0]


def test_poll_batch_times_out() -> None:
    batches = MagicMock()
    batches.retrieve.return_value = _FakeBatchRecord("b1", "in_progress")
    client = _client_with_batches(batches)
    status, polls = poll_batch(client, "b1", interval_seconds=0.01, max_polls=3, sleep=lambda _s: None)
    assert status == "timed_out"
    assert polls == 3


def test_iter_batch_results_extracts_text() -> None:
    batches = MagicMock()
    batches.results.return_value = iter(
        [
            _FakeResultEntry("a", "positive"),
            _FakeResultEntry("b", "neutral"),
        ]
    )
    client = _client_with_batches(batches)
    results = iter_batch_results(client, "b1")
    assert len(results) == 2
    assert results[0]["custom_id"] == "a"
    assert results[0]["text"] == "positive"
    assert results[0]["result_type"] == "succeeded"


def test_run_batch_end_to_end() -> None:
    batches = MagicMock()
    batches.create.return_value = _FakeBatchRecord("bX", "in_progress")
    batches.retrieve.side_effect = [
        _FakeBatchRecord("bX", "in_progress"),
        _FakeBatchRecord("bX", "ended"),
    ]
    batches.results.return_value = [
        _FakeResultEntry("eval-0001", "positive"),
        _FakeResultEntry("eval-0002", "negative"),
    ]
    client = _client_with_batches(batches)
    reqs = build_batch_requests([("eval-0001", "x"), ("eval-0002", "y")], model="m")
    outcome = run_batch(client, reqs, interval_seconds=0.0, sleep=lambda _s: None)
    assert outcome.batch_id == "bX"
    assert outcome.status == "ended"
    assert len(outcome.results) == 2


def test_shipped_batch_input_jsonl_is_parseable() -> None:
    path = Path(__file__).parent / "batch_input.jsonl"
    entries = load_batch_jsonl(path)
    assert len(entries) == 100
    assert entries[0]["custom_id"] == "eval-0000"
    assert entries[0]["params"]["messages"][0]["role"] == "user"
