"""Tests for recipe 05."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from common.client import CookbookClient
from recipes._fixtures import FakeTextBlock, FakeUsage, build_response

from .recipe import build_cacheable_system, compare_runs, measure_once


def _client(*responses: Any) -> CookbookClient:
    raw = MagicMock()
    raw.messages.create.side_effect = list(responses)
    return CookbookClient.with_raw_client(raw)


def test_system_prompt_has_exactly_one_cache_control_block() -> None:
    system = build_cacheable_system()
    breakpoints = [b for b in system if b.get("cache_control")]
    assert len(breakpoints) == 1
    assert breakpoints[0]["cache_control"] == {"type": "ephemeral"}


def test_system_prompt_places_cache_on_the_handbook_block() -> None:
    system = build_cacheable_system()
    # Short preamble first (uncached), long handbook second (cached)
    assert "Atlas" in system[0]["text"]
    assert "cache_control" not in system[0]
    assert "Handbook" in system[1]["text"]
    assert system[1]["cache_control"] == {"type": "ephemeral"}


def test_measure_once_reports_cache_creation_on_first_request() -> None:
    response = build_response(
        content=[FakeTextBlock("Summary.")],
        usage=FakeUsage(
            in_tok=1200,
            out_tok=30,
            cache_read=0,
            cache_write=1100,
        ),
        stop_reason="end_turn",
    )
    client = _client(response)
    measurement = measure_once(client, user_prompt="Summarize Section 01")
    assert measurement.cache_creation_input_tokens == 1100
    assert measurement.cache_read_input_tokens == 0
    assert measurement.cost_usd > 0


def test_compare_runs_reports_reuse_on_subsequent_requests() -> None:
    first = build_response(
        content=[FakeTextBlock("first")],
        usage=FakeUsage(1200, 30, cache_read=0, cache_write=1100),
    )
    second = build_response(
        content=[FakeTextBlock("second")],
        usage=FakeUsage(1200, 30, cache_read=1100, cache_write=0),
    )
    third = build_response(
        content=[FakeTextBlock("third")],
        usage=FakeUsage(1200, 30, cache_read=1100, cache_write=0),
    )
    client = _client(first, second, third)
    report = compare_runs(client)
    assert report["summary"]["total_requests"] == 3
    assert report["summary"]["cache_write_tokens"] == 1100
    assert report["summary"]["cache_read_tokens_total"] == 2200
    assert report["summary"]["estimated_prefix_reuse_pct"] == pytest.approx(100.0)


def test_compare_runs_reports_zero_reuse_when_cache_misses() -> None:
    # Every request writes anew — no hits
    r1 = build_response(
        content=[FakeTextBlock("a")],
        usage=FakeUsage(1200, 30, cache_read=0, cache_write=1100),
    )
    r2 = build_response(
        content=[FakeTextBlock("b")],
        usage=FakeUsage(1200, 30, cache_read=0, cache_write=1100),
    )
    client = _client(r1, r2)
    report = compare_runs(client, prompts=["a", "b"])
    assert report["summary"]["cache_read_tokens_total"] == 0
    assert report["summary"]["estimated_prefix_reuse_pct"] == 0.0
