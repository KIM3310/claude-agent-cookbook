"""Tests for recipe 08."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from common.client import CookbookClient
from recipes._fixtures import FakeTextBlock, FakeToolUseBlock, FakeUsage, build_response

from .recipe import (
    build_specialist_tools,
    coordinate,
    make_specialist,
    run_launch,
)


def _sequence_client(responses: list[Any]) -> CookbookClient:
    raw = MagicMock()
    raw.messages.create.side_effect = list(responses)
    return CookbookClient.with_raw_client(raw)


def _coordinator_response(tool_blocks: list[Any], *, stop: str = "tool_use") -> Any:
    return build_response(content=tool_blocks, usage=FakeUsage(200, 80), stop_reason=stop)


def _specialist_response(text: str) -> Any:
    return build_response(
        content=[FakeTextBlock(text)],
        usage=FakeUsage(50, 30),
        stop_reason="end_turn",
    )


def test_specialist_factory_calls_with_correct_system_prompt() -> None:
    raw = MagicMock()
    raw.messages.create.return_value = build_response(
        content=[FakeTextBlock("notes")],
        usage=FakeUsage(10, 5),
    )
    client = CookbookClient.with_raw_client(raw)
    spec = make_specialist(client, system="you are a researcher")
    result = spec("brief text")
    assert result == "notes"
    kwargs = raw.messages.create.call_args.kwargs
    assert kwargs["system"] == "you are a researcher"
    assert kwargs["messages"][0]["content"] == "brief text"


def test_build_specialist_tools_registers_three_tools() -> None:
    registry, _ = build_specialist_tools(
        research=lambda _p: "",
        copywriter=lambda _p: "",
        engineer=lambda _p: "",
    )
    assert registry.names() == ["research", "copywriter", "engineer"]


def test_coordinate_delegates_to_specialists_and_synthesizes() -> None:
    # Responses in order:
    # 1) coordinator calls research
    # 2) specialist response isn't routed through messages.create in this test
    #    because we pass specialist callables as plain fns.
    # 3) coordinator calls copywriter
    # 4) coordinator calls engineer
    # 5) coordinator produces the final markdown
    coord_responses = [
        _coordinator_response(
            [FakeToolUseBlock(id_="t1", name="research", input_={"brief": "b" * 30})]
        ),
        _coordinator_response(
            [
                FakeToolUseBlock(
                    id_="t2",
                    name="copywriter",
                    input_={"brief": "b" * 30, "positioning_notes": "notes from research"},
                )
            ]
        ),
        _coordinator_response(
            [FakeToolUseBlock(id_="t3", name="engineer", input_={"brief": "b" * 30})]
        ),
        build_response(
            content=[
                FakeTextBlock(
                    "## Positioning\nA\n\n## Copy\nB\n\n## Engineering plan\nC\n"
                )
            ],
            usage=FakeUsage(120, 90),
            stop_reason="end_turn",
        ),
    ]
    client = _sequence_client(coord_responses)
    registry, trace = build_specialist_tools(
        research=lambda _p: "notes from research",
        copywriter=lambda _p: "draft copy",
        engineer=lambda _p: "1. infra 2. data",
    )
    outcome = coordinate("b" * 30, client=client, registry=registry, trace=trace)
    assert outcome.iterations == 4
    assert "## Positioning" in outcome.final_document
    specialists = [t.specialist for t in outcome.trace]
    assert specialists == ["research", "copywriter", "engineer"]


def test_coordinate_stops_on_budget() -> None:
    loops = [
        _coordinator_response(
            [FakeToolUseBlock(id_=f"t{i}", name="research", input_={"brief": "b" * 30})]
        )
        for i in range(10)
    ]
    client = _sequence_client(loops)
    registry, trace = build_specialist_tools(
        research=lambda _p: "notes",
        copywriter=lambda _p: "",
        engineer=lambda _p: "",
    )
    outcome = coordinate("b" * 30, client=client, registry=registry, trace=trace, max_iterations=3)
    assert outcome.iterations == 3
    assert "iteration budget" in outcome.final_document


def test_run_launch_uses_same_client_for_coordinator_and_specialists() -> None:
    """Each specialist + coordinator response shares one Claude client."""
    # One call per specialist handler + coordinator rounds
    # Order of Claude calls inside the coordinator loop:
    # coordinator -> tool_use(research) -> specialist research (client call)
    # coordinator -> tool_use(copywriter) -> specialist copywriter (client call)
    # coordinator -> tool_use(engineer) -> specialist engineer (client call)
    # coordinator -> final text
    responses = [
        _coordinator_response(
            [FakeToolUseBlock(id_="t1", name="research", input_={"brief": "b" * 30})]
        ),
        _specialist_response("notes"),
        _coordinator_response(
            [FakeToolUseBlock(id_="t2", name="copywriter", input_={"brief": "b" * 30, "positioning_notes": "notes"})]
        ),
        _specialist_response("copy"),
        _coordinator_response(
            [FakeToolUseBlock(id_="t3", name="engineer", input_={"brief": "b" * 30})]
        ),
        _specialist_response("plan"),
        build_response(
            content=[FakeTextBlock("## Positioning\n...\n## Copy\n...\n## Engineering plan\n...")],
            usage=FakeUsage(120, 90),
            stop_reason="end_turn",
        ),
    ]
    client = _sequence_client(responses)
    outcome = run_launch("b" * 30, client=client)
    # 4 coordinator calls + 3 specialist calls = 7 total
    assert client.ledger.summary()["requests"] == 7
    assert len(outcome.trace) == 3
