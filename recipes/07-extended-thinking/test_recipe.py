"""Tests for recipe 07."""

from __future__ import annotations

from unittest.mock import MagicMock

from common.client import CookbookClient
from recipes._fixtures import FakeTextBlock, FakeThinkingBlock, FakeUsage, build_response

from .recipe import _split_thinking_and_text, solve_with_thinking


def _client(*responses: object) -> CookbookClient:
    raw = MagicMock()
    raw.messages.create.side_effect = list(responses)
    return CookbookClient.with_raw_client(raw)


def test_split_thinking_and_text_handles_mixed_blocks() -> None:
    blocks = [
        FakeThinkingBlock("Let me enumerate constraints..."),
        FakeTextBlock("Here is the itinerary:"),
        FakeThinkingBlock("...additional chain of thought..."),
        FakeTextBlock("- Day 1: Seoul -> SFO"),
    ]
    visible, thinking = _split_thinking_and_text(blocks)
    assert "itinerary" in visible
    assert "Day 1" in visible
    assert "enumerate" in thinking
    assert "additional" in thinking
    assert "Let me" not in visible


def test_solve_with_thinking_forwards_thinking_parameter() -> None:
    raw = MagicMock()
    raw.messages.create.return_value = build_response(
        content=[FakeThinkingBlock("deliberation..."), FakeTextBlock("final answer")],
        usage=FakeUsage(400, 100),
        stop_reason="end_turn",
    )
    client = CookbookClient.with_raw_client(raw)
    result = solve_with_thinking("problem", client=client, thinking_budget_tokens=2048)
    kwargs = raw.messages.create.call_args.kwargs
    assert kwargs["thinking"] == {"type": "enabled", "budget_tokens": 2048}
    assert result.visible_answer == "final answer"
    assert result.thinking_chars == len("deliberation...")


def test_solve_with_thinking_never_leaks_thinking_into_visible() -> None:
    raw = MagicMock()
    raw.messages.create.return_value = build_response(
        content=[
            FakeThinkingBlock("SECRET INTERNAL REASONING SHOULD NOT ESCAPE"),
            FakeTextBlock("Here is the plan."),
        ],
        usage=FakeUsage(100, 50),
    )
    client = CookbookClient.with_raw_client(raw)
    result = solve_with_thinking("problem", client=client)
    assert "SECRET" not in result.visible_answer
    assert "SECRET" in result.thinking_summary


def test_solve_with_thinking_truncates_summary_to_400_chars() -> None:
    long_thinking = "x" * 1500
    raw = MagicMock()
    raw.messages.create.return_value = build_response(
        content=[FakeThinkingBlock(long_thinking), FakeTextBlock("answer")],
        usage=FakeUsage(100, 50),
    )
    client = CookbookClient.with_raw_client(raw)
    result = solve_with_thinking("p", client=client)
    assert len(result.thinking_summary) == 400
    assert result.thinking_chars == 1500


def test_solve_with_thinking_handles_empty_thinking_block() -> None:
    # Some models may return empty thinking; recipe should still surface the answer.
    raw = MagicMock()
    raw.messages.create.return_value = build_response(
        content=[FakeTextBlock("direct answer")],
        usage=FakeUsage(50, 10),
    )
    client = CookbookClient.with_raw_client(raw)
    result = solve_with_thinking("p", client=client)
    assert result.thinking_chars == 0
    assert result.visible_answer == "direct answer"
