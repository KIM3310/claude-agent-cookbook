"""Recipe 01: single-turn tool use with Claude.

Pattern:

    user question -> Claude decides to call a tool -> local handler runs
    -> tool_result flows back to Claude -> Claude produces final natural
    language answer.

This recipe demonstrates the minimum viable tool-use loop. It also shows the
two error modes production systems must handle:

1. Claude requests arguments that fail Pydantic validation. We return a
   ``tool_result`` with ``is_error=True`` so Claude can self-correct.
2. The tool handler itself raises. We catch the exception, report the error
   as a structured tool result, and let Claude decide whether to retry or
   surface the failure to the user.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from common.client import CookbookClient
from common.logging import get_logger, setup_logging
from common.tools import ToolArgumentError, ToolDefinition, ToolRegistry

logger = get_logger(__name__)


SYSTEM_PROMPT = (
    "You are a concise weather assistant. When a user asks about the weather "
    "in a city, call the `get_weather` tool exactly once. After receiving the "
    "tool result, respond in a single sentence with the temperature and a "
    "brief description. Do not invent data."
)


# ---------------------------------------------------------------------------
# Tool definition
# ---------------------------------------------------------------------------


class GetWeatherArgs(BaseModel):
    city: str = Field(..., description="City name, for example 'Seoul' or 'San Francisco'.")
    unit: str = Field(
        "celsius",
        description="Temperature unit. One of: 'celsius', 'fahrenheit'.",
    )


# A tiny deterministic fixture lets the recipe run and be tested without a real
# weather API. Swap this with httpx to a real endpoint for production use.
_WEATHER_FIXTURE: dict[str, dict[str, Any]] = {
    "seoul": {"temperature_c": 22.0, "conditions": "clear"},
    "san francisco": {"temperature_c": 16.0, "conditions": "foggy"},
    "tokyo": {"temperature_c": 24.0, "conditions": "partly cloudy"},
    "london": {"temperature_c": 12.0, "conditions": "rainy"},
}


def get_weather(args: GetWeatherArgs) -> dict[str, Any]:
    """Look up weather from the in-memory fixture.

    In production this would call a real weather API. Keeping the signature
    pure (args in, dict out) keeps the recipe easy to unit-test.
    """
    record = _WEATHER_FIXTURE.get(args.city.lower())
    if record is None:
        raise ValueError(f"No weather data available for {args.city!r}")
    temp_c = record["temperature_c"]
    temp = temp_c if args.unit == "celsius" else (temp_c * 9 / 5) + 32
    return {
        "city": args.city,
        "unit": args.unit,
        "temperature": round(temp, 1),
        "conditions": record["conditions"],
    }


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="get_weather",
            description="Look up current weather for a city by name.",
            args_model=GetWeatherArgs,
            handler=get_weather,
        )
    )
    return registry


# ---------------------------------------------------------------------------
# Tool-use loop (single turn)
# ---------------------------------------------------------------------------


def _extract_tool_use_blocks(content: Any) -> list[Any]:
    """Return the list of ``tool_use`` content blocks in a response."""
    blocks: list[Any] = []
    for block in content or []:
        block_type = getattr(block, "type", None) or (
            block.get("type") if isinstance(block, dict) else None
        )
        if block_type == "tool_use":
            blocks.append(block)
    return blocks


def _block_attr(block: Any, name: str) -> Any:
    if isinstance(block, dict):
        return block.get(name)
    return getattr(block, name, None)


def _run_tool_call(registry: ToolRegistry, block: Any) -> dict[str, Any]:
    """Execute a single tool call, returning a ``tool_result`` content block."""
    tool_use_id = _block_attr(block, "id")
    tool_name = _block_attr(block, "name")
    tool_input = _block_attr(block, "input") or {}
    try:
        output = registry.invoke(tool_name, tool_input)
        return {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": json.dumps(output),
        }
    except ToolArgumentError as exc:
        logger.warning(
            "tool.argument_error",
            extra={"tool": tool_name, "input": tool_input, "error": str(exc)},
        )
        return {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": f"Invalid arguments: {exc}. Please reformat the call.",
            "is_error": True,
        }
    except Exception as exc:  # noqa: BLE001 — we want to surface anything to Claude
        logger.exception("tool.handler_error", extra={"tool": tool_name})
        return {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": f"Tool failed: {type(exc).__name__}: {exc}",
            "is_error": True,
        }


def run(prompt: str, *, client: CookbookClient, registry: ToolRegistry) -> dict[str, Any]:
    """Run one turn of tool-use for ``prompt`` and return a structured result."""

    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
    first = client.create_message(
        messages=messages,
        system=SYSTEM_PROMPT,
        tools=registry.to_anthropic(),
        max_tokens=512,
    )

    tool_calls = _extract_tool_use_blocks(first.raw.content if first.raw else [])
    tool_outputs: list[dict[str, Any]] = []

    if not tool_calls or first.stop_reason != "tool_use":
        # Claude answered without tools — return the text verbatim.
        return {
            "prompt": prompt,
            "tool_calls": [],
            "final_text": first.text,
            "stop_reason": first.stop_reason,
            "usage": client.ledger.summary(),
        }

    # Execute every tool_use block Claude emitted in a single assistant turn.
    tool_results: list[dict[str, Any]] = []
    for block in tool_calls:
        result_block = _run_tool_call(registry, block)
        tool_results.append(result_block)
        tool_outputs.append(
            {
                "tool": _block_attr(block, "name"),
                "input": _block_attr(block, "input"),
                "output": result_block["content"],
                "is_error": result_block.get("is_error", False),
            }
        )

    # Append the assistant turn and the matching tool_result user turn, then
    # ask Claude to produce the final natural-language answer.
    messages.append({"role": "assistant", "content": first.raw.content})
    messages.append({"role": "user", "content": tool_results})
    second = client.create_message(
        messages=messages,
        system=SYSTEM_PROMPT,
        tools=registry.to_anthropic(),
        max_tokens=512,
    )
    return {
        "prompt": prompt,
        "tool_calls": tool_outputs,
        "final_text": second.text,
        "stop_reason": second.stop_reason,
        "usage": client.ledger.summary(),
    }


def _cli() -> int:
    parser = argparse.ArgumentParser(description="Recipe 01 — single-turn tool use")
    parser.add_argument("--prompt", default="What's the weather in Seoul right now?")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    setup_logging()
    client = CookbookClient()
    registry = build_registry()
    result = run(args.prompt, client=client, registry=registry)
    rendered = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
