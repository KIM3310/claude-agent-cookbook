"""Recipe 02: multi-turn tool use with convergence detection.

Task: "book me a flight to Tokyo next Tuesday." The agent needs three tools:

- ``search_flights`` — list flights matching origin/destination/date.
- ``compare_options`` — rank candidates by price and duration.
- ``hold_booking`` — place a non-binding hold on the selected flight.

This recipe demonstrates the multi-turn loop:

1. Claude calls ``search_flights``.
2. Claude receives results, calls ``compare_options``.
3. Claude receives the ranking, calls ``hold_booking``.
4. Claude finalizes the conversation (stop_reason=end_turn).

Two production concerns are made explicit:

- **Convergence detection** — we cap the loop with ``max_iterations`` and stop
  cleanly when ``stop_reason == "end_turn"``.
- **Budget control** — each iteration increments a budget counter; if the
  model keeps calling tools past the budget, we bail and surface a structured
  error instead of looping forever.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

from common.client import CookbookClient
from common.logging import get_logger, setup_logging
from common.tools import ToolArgumentError, ToolDefinition, ToolRegistry

logger = get_logger(__name__)


SYSTEM_PROMPT = (
    "You are a flight-booking assistant. Follow this workflow strictly:\n"
    "1. Call `search_flights` once with the user's origin, destination, and "
    "date.\n"
    "2. Call `compare_options` on the returned flight ids to rank them by a "
    "weighted score of price and duration.\n"
    "3. Call `hold_booking` on the top-ranked option.\n"
    "4. Reply in one short paragraph confirming the hold, including the "
    "booking reference and flight id.\n"
    "Never invent flight data. If any step fails, stop and explain the failure."
)


# ---------------------------------------------------------------------------
# Tool argument models
# ---------------------------------------------------------------------------


class SearchFlightsArgs(BaseModel):
    origin: str = Field(..., description="IATA code, e.g. ICN.")
    destination: str = Field(..., description="IATA code, e.g. HND.")
    depart_date: str = Field(..., description="ISO date, YYYY-MM-DD.")

    @field_validator("origin", "destination")
    @classmethod
    def _iata(cls, value: str) -> str:
        if len(value) != 3 or not value.isalpha():
            raise ValueError("IATA code must be three letters")
        return value.upper()

    @field_validator("depart_date")
    @classmethod
    def _iso_date(cls, value: str) -> str:
        date.fromisoformat(value)  # raises on bad format
        return value


class CompareOptionsArgs(BaseModel):
    flight_ids: list[str] = Field(..., min_length=2, description="Flight ids to compare")
    price_weight: float = Field(0.6, ge=0.0, le=1.0)
    duration_weight: float = Field(0.4, ge=0.0, le=1.0)


class HoldBookingArgs(BaseModel):
    flight_id: str = Field(..., description="Flight id returned by search_flights")
    passenger_name: str = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# Deterministic fixtures (replace with real integrations in production)
# ---------------------------------------------------------------------------


_FLIGHT_FIXTURE: dict[tuple[str, str, str], list[dict[str, Any]]] = {
    ("ICN", "HND", "2026-04-21"): [
        {"id": "KE2711", "price_usd": 420, "duration_minutes": 135, "carrier": "Korean Air"},
        {"id": "OZ1055", "price_usd": 395, "duration_minutes": 140, "carrier": "Asiana"},
        {"id": "JL92", "price_usd": 475, "duration_minutes": 130, "carrier": "JAL"},
    ],
}


def search_flights(args: SearchFlightsArgs) -> dict[str, Any]:
    key = (args.origin, args.destination, args.depart_date)
    results = _FLIGHT_FIXTURE.get(key, [])
    return {
        "origin": args.origin,
        "destination": args.destination,
        "depart_date": args.depart_date,
        "results": results,
    }


def compare_options(args: CompareOptionsArgs) -> dict[str, Any]:
    catalog = {f["id"]: f for options in _FLIGHT_FIXTURE.values() for f in options}
    missing = [fid for fid in args.flight_ids if fid not in catalog]
    if missing:
        raise ValueError(f"Unknown flight ids: {missing}")
    subset = [catalog[fid] for fid in args.flight_ids]
    max_price = max(f["price_usd"] for f in subset)
    max_duration = max(f["duration_minutes"] for f in subset)
    ranked = sorted(
        subset,
        key=lambda f: (
            args.price_weight * (f["price_usd"] / max_price)
            + args.duration_weight * (f["duration_minutes"] / max_duration)
        ),
    )
    return {"ranking": [f["id"] for f in ranked], "details": ranked}


def hold_booking(args: HoldBookingArgs) -> dict[str, Any]:
    # Stable, non-random reference so tests are deterministic
    reference = f"HLD-{args.flight_id}-{abs(hash(args.passenger_name)) % 100000:05d}"
    return {
        "flight_id": args.flight_id,
        "passenger_name": args.passenger_name,
        "hold_reference": reference,
        "expires_in_minutes": 30,
    }


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="search_flights",
            description="Search flights by origin, destination, and departure date.",
            args_model=SearchFlightsArgs,
            handler=search_flights,
        )
    )
    registry.register(
        ToolDefinition(
            name="compare_options",
            description="Rank flight ids by weighted price and duration.",
            args_model=CompareOptionsArgs,
            handler=compare_options,
        )
    )
    registry.register(
        ToolDefinition(
            name="hold_booking",
            description="Place a 30-minute non-binding hold on a flight.",
            args_model=HoldBookingArgs,
            handler=hold_booking,
        )
    )
    return registry


# ---------------------------------------------------------------------------
# Multi-turn loop
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class LoopOutcome:
    reason: str  # "converged" | "budget_exhausted" | "error"
    final_text: str
    iterations: int
    tool_trace: list[dict[str, Any]] = field(default_factory=list)


def _extract_tool_use_blocks(content: Any) -> list[Any]:
    return [
        b
        for b in (content or [])
        if (getattr(b, "type", None) or (b.get("type") if isinstance(b, dict) else None))
        == "tool_use"
    ]


def _block_attr(block: Any, name: str) -> Any:
    if isinstance(block, dict):
        return block.get(name)
    return getattr(block, name, None)


def _run_tool(registry: ToolRegistry, block: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    tool_use_id = _block_attr(block, "id")
    name = _block_attr(block, "name")
    tool_input = _block_attr(block, "input") or {}
    try:
        output = registry.invoke(name, tool_input)
        return (
            {
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": json.dumps(output, default=str),
            },
            {"tool": name, "input": tool_input, "output": output, "is_error": False},
        )
    except ToolArgumentError as exc:
        trace = {"tool": name, "input": tool_input, "error": str(exc), "is_error": True}
        return (
            {
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": f"Invalid arguments: {exc}",
                "is_error": True,
            },
            trace,
        )
    except Exception as exc:  # noqa: BLE001 — surface to Claude
        trace = {"tool": name, "input": tool_input, "error": str(exc), "is_error": True}
        return (
            {
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": f"{type(exc).__name__}: {exc}",
                "is_error": True,
            },
            trace,
        )


def run_agent(
    prompt: str,
    *,
    client: CookbookClient,
    registry: ToolRegistry,
    max_iterations: int = 6,
) -> LoopOutcome:
    """Run the multi-turn tool-use loop until convergence or budget exhaustion."""

    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
    tool_trace: list[dict[str, Any]] = []

    for iteration in range(1, max_iterations + 1):
        response = client.create_message(
            messages=messages,
            system=SYSTEM_PROMPT,
            tools=registry.to_anthropic(),
            max_tokens=1024,
        )

        # Convergence: no more tool calls
        if response.stop_reason != "tool_use":
            return LoopOutcome(
                reason="converged",
                final_text=response.text,
                iterations=iteration,
                tool_trace=tool_trace,
            )

        raw_content = response.raw.content if response.raw else []
        tool_uses = _extract_tool_use_blocks(raw_content)
        if not tool_uses:
            # stop_reason was tool_use but no tool blocks? Defensive exit.
            return LoopOutcome(
                reason="error",
                final_text="Claude reported tool_use without a tool_use block.",
                iterations=iteration,
                tool_trace=tool_trace,
            )

        results: list[dict[str, Any]] = []
        for block in tool_uses:
            result_block, trace_entry = _run_tool(registry, block)
            results.append(result_block)
            tool_trace.append({**trace_entry, "iteration": iteration})

        messages.append({"role": "assistant", "content": raw_content})
        messages.append({"role": "user", "content": results})

    return LoopOutcome(
        reason="budget_exhausted",
        final_text=(
            "Maximum tool-use iterations reached without a final answer. "
            "Inspect tool_trace to debug."
        ),
        iterations=max_iterations,
        tool_trace=tool_trace,
    )


def _cli() -> int:
    parser = argparse.ArgumentParser(description="Recipe 02 — multi-turn tool use")
    parser.add_argument(
        "--prompt",
        default=(
            "Book me a flight from ICN to HND on 2026-04-21. Passenger: Doeon Kim. "
            "Use the standard workflow."
        ),
    )
    parser.add_argument("--max-iterations", type=int, default=6)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    setup_logging()
    client = CookbookClient()
    registry = build_registry()
    outcome = run_agent(args.prompt, client=client, registry=registry, max_iterations=args.max_iterations)
    result = {
        "reason": outcome.reason,
        "iterations": outcome.iterations,
        "final_text": outcome.final_text,
        "tool_trace": outcome.tool_trace,
        "usage": client.ledger.summary(),
    }
    rendered = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
