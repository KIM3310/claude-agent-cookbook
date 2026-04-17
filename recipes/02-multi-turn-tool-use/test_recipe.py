"""Tests for recipe 02."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from common.client import CookbookClient
from recipes._fixtures import FakeTextBlock, FakeToolUseBlock, FakeUsage, build_response

from .recipe import (
    CompareOptionsArgs,
    HoldBookingArgs,
    SearchFlightsArgs,
    build_registry,
    compare_options,
    hold_booking,
    run_agent,
    search_flights,
)


def _client(*responses: Any) -> CookbookClient:
    raw = MagicMock()
    raw.messages.create.side_effect = list(responses)
    return CookbookClient.with_raw_client(raw)


def test_search_args_reject_bad_iata() -> None:
    with pytest.raises(ValidationError):
        SearchFlightsArgs(origin="Seoul", destination="HND", depart_date="2026-04-21")


def test_search_returns_three_options() -> None:
    out = search_flights(SearchFlightsArgs(origin="ICN", destination="HND", depart_date="2026-04-21"))
    assert len(out["results"]) == 3
    ids = {f["id"] for f in out["results"]}
    assert ids == {"KE2711", "OZ1055", "JL92"}


def test_compare_options_ranks_cheapest_first() -> None:
    ranked = compare_options(
        CompareOptionsArgs(flight_ids=["KE2711", "OZ1055", "JL92"], price_weight=1.0, duration_weight=0.0)
    )
    assert ranked["ranking"][0] == "OZ1055"


def test_compare_options_rejects_unknown_id() -> None:
    with pytest.raises(ValueError):
        compare_options(CompareOptionsArgs(flight_ids=["KE2711", "XX9999"]))


def test_hold_booking_is_deterministic() -> None:
    r1 = hold_booking(HoldBookingArgs(flight_id="KE2711", passenger_name="Doeon"))
    r2 = hold_booking(HoldBookingArgs(flight_id="KE2711", passenger_name="Doeon"))
    assert r1["hold_reference"] == r2["hold_reference"]


def test_run_agent_converges_after_three_tool_calls() -> None:
    search = FakeToolUseBlock(
        id_="t1",
        name="search_flights",
        input_={"origin": "ICN", "destination": "HND", "depart_date": "2026-04-21"},
    )
    compare = FakeToolUseBlock(
        id_="t2",
        name="compare_options",
        input_={"flight_ids": ["KE2711", "OZ1055", "JL92"]},
    )
    hold = FakeToolUseBlock(
        id_="t3",
        name="hold_booking",
        input_={"flight_id": "OZ1055", "passenger_name": "Doeon Kim"},
    )
    final = FakeTextBlock("Held OZ1055 for Doeon Kim. Reference available.")

    responses = [
        build_response(content=[search], usage=FakeUsage(120, 30), stop_reason="tool_use"),
        build_response(content=[compare], usage=FakeUsage(140, 40), stop_reason="tool_use"),
        build_response(content=[hold], usage=FakeUsage(160, 45), stop_reason="tool_use"),
        build_response(content=[final], usage=FakeUsage(180, 55), stop_reason="end_turn"),
    ]
    client = _client(*responses)
    outcome = run_agent("Book ICN->HND 2026-04-21", client=client, registry=build_registry())

    assert outcome.reason == "converged"
    assert outcome.iterations == 4
    assert [t["tool"] for t in outcome.tool_trace] == [
        "search_flights",
        "compare_options",
        "hold_booking",
    ]
    assert not any(t["is_error"] for t in outcome.tool_trace)


def test_run_agent_stops_on_budget_exhaustion() -> None:
    # Claude keeps calling search_flights forever
    looping = FakeToolUseBlock(
        id_="loop",
        name="search_flights",
        input_={"origin": "ICN", "destination": "HND", "depart_date": "2026-04-21"},
    )
    responses = [
        build_response(content=[looping], usage=FakeUsage(10, 5), stop_reason="tool_use")
        for _ in range(10)
    ]
    client = _client(*responses)
    outcome = run_agent(
        "Book ICN->HND 2026-04-21",
        client=client,
        registry=build_registry(),
        max_iterations=3,
    )
    assert outcome.reason == "budget_exhausted"
    assert outcome.iterations == 3
    assert len(outcome.tool_trace) == 3


def test_run_agent_reports_tool_errors_in_trace() -> None:
    bad_call = FakeToolUseBlock(
        id_="bad",
        name="compare_options",
        input_={"flight_ids": ["KE2711", "XX9999"]},
    )
    apology = FakeTextBlock("I could not compare those flights; one is unknown.")
    responses = [
        build_response(content=[bad_call], usage=FakeUsage(10, 5), stop_reason="tool_use"),
        build_response(content=[apology], usage=FakeUsage(12, 6), stop_reason="end_turn"),
    ]
    client = _client(*responses)
    outcome = run_agent("Compare flights", client=client, registry=build_registry())
    assert outcome.reason == "converged"
    assert outcome.tool_trace[0]["is_error"] is True
