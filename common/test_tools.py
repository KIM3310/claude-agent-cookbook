"""Tests for :mod:`common.tools`."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, Field

from common.tools import ToolArgumentError, ToolDefinition, ToolRegistry


class _WeatherArgs(BaseModel):
    city: str = Field(..., description="City name")
    unit: str = Field("celsius", description="celsius or fahrenheit")


def _weather_handler(args: _WeatherArgs) -> dict[str, str]:
    return {"city": args.city, "unit": args.unit, "temp": "22"}


def _make_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="get_weather",
            description="Look up current weather for a city.",
            args_model=_WeatherArgs,
            handler=_weather_handler,
        )
    )
    return registry


def test_tool_definition_generates_clean_schema() -> None:
    tool = _make_registry().get("get_weather")
    schema = tool.input_schema()
    assert "title" not in schema
    assert schema["type"] == "object"
    assert "city" in schema["properties"]
    assert "title" not in schema["properties"]["city"]


def test_registry_to_anthropic_shape() -> None:
    tools = _make_registry().to_anthropic()
    assert len(tools) == 1
    assert tools[0]["name"] == "get_weather"
    assert tools[0]["description"].startswith("Look up")
    assert tools[0]["input_schema"]["properties"]["city"]["type"] == "string"


def test_registry_invokes_handler_with_validated_args() -> None:
    registry = _make_registry()
    result = registry.invoke("get_weather", {"city": "Seoul"})
    assert result == {"city": "Seoul", "unit": "celsius", "temp": "22"}


def test_registry_raises_tool_argument_error_on_bad_input() -> None:
    registry = _make_registry()
    with pytest.raises(ToolArgumentError) as excinfo:
        registry.invoke("get_weather", {"unit": "kelvin"})  # city missing
    assert excinfo.value.tool_name == "get_weather"


def test_registry_rejects_duplicate_registration() -> None:
    registry = _make_registry()
    with pytest.raises(ValueError):
        registry.register(
            ToolDefinition(
                name="get_weather",
                description="dup",
                args_model=_WeatherArgs,
                handler=_weather_handler,
            )
        )


def test_registry_unknown_tool_helpful_error() -> None:
    registry = _make_registry()
    with pytest.raises(KeyError) as excinfo:
        registry.get("nope")
    assert "get_weather" in str(excinfo.value)
