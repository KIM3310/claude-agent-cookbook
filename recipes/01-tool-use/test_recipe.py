"""Tests for recipe 01. No API key required."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from common.client import CookbookClient
from recipes._fixtures import FakeTextBlock, FakeToolUseBlock, FakeUsage, build_response

from .recipe import GetWeatherArgs, build_registry, get_weather, run


def _client(*responses: object) -> CookbookClient:
    raw = MagicMock()
    raw.messages.create.side_effect = list(responses)
    return CookbookClient.with_raw_client(raw)


def test_get_weather_handler_returns_expected_payload() -> None:
    payload = get_weather(GetWeatherArgs(city="Seoul"))
    assert payload["city"] == "Seoul"
    assert payload["unit"] == "celsius"
    assert payload["conditions"] == "clear"


def test_get_weather_unit_conversion() -> None:
    payload = get_weather(GetWeatherArgs(city="Seoul", unit="fahrenheit"))
    assert payload["unit"] == "fahrenheit"
    # 22C -> 71.6F
    assert payload["temperature"] == pytest.approx(71.6)


def test_get_weather_unknown_city_raises() -> None:
    with pytest.raises(ValueError):
        get_weather(GetWeatherArgs(city="Atlantis"))


def test_registry_exposes_expected_schema() -> None:
    tools = build_registry().to_anthropic()
    assert len(tools) == 1
    tool = tools[0]
    assert tool["name"] == "get_weather"
    assert tool["input_schema"]["properties"]["city"]["type"] == "string"


def test_run_with_single_tool_call() -> None:
    tool_use = FakeToolUseBlock(id_="toolu_01", name="get_weather", input_={"city": "Seoul"})
    first = build_response(
        content=[FakeTextBlock("Let me check."), tool_use],
        usage=FakeUsage(10, 5),
        stop_reason="tool_use",
    )
    second = build_response(
        content=[FakeTextBlock("Seoul is 22C and clear.")],
        usage=FakeUsage(20, 10),
        stop_reason="end_turn",
    )
    client = _client(first, second)
    result = run("weather in Seoul?", client=client, registry=build_registry())

    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0]["tool"] == "get_weather"
    assert "Seoul" in result["final_text"]
    assert result["stop_reason"] == "end_turn"
    assert result["usage"]["requests"] == 2


def test_run_surfaces_tool_handler_error_to_claude() -> None:
    """When a tool handler raises, the error should flow into Claude as a tool_result."""
    tool_use = FakeToolUseBlock(id_="toolu_02", name="get_weather", input_={"city": "Atlantis"})
    first = build_response(
        content=[tool_use],
        usage=FakeUsage(10, 5),
        stop_reason="tool_use",
    )
    second = build_response(
        content=[FakeTextBlock("I could not find weather for Atlantis.")],
        usage=FakeUsage(12, 6),
        stop_reason="end_turn",
    )
    client = _client(first, second)
    result = run("weather in Atlantis?", client=client, registry=build_registry())
    assert result["tool_calls"][0]["is_error"] is True
    assert "Atlantis" in result["final_text"]


def test_run_returns_early_when_claude_does_not_use_tools() -> None:
    only_text = build_response(
        content=[FakeTextBlock("I have no weather to share.")],
        usage=FakeUsage(5, 2),
        stop_reason="end_turn",
    )
    client = _client(only_text)
    result = run("hi", client=client, registry=build_registry())
    assert result["tool_calls"] == []
    assert result["final_text"].startswith("I have no")
    assert result["usage"]["requests"] == 1
