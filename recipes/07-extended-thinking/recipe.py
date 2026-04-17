"""Recipe 07: extended thinking for hard reasoning problems.

Enabling extended thinking asks Claude to produce hidden reasoning before
the final answer. For planning, algebra, and deep code review this
demonstrably improves accuracy at the cost of latency and output tokens.

Usage shape (SDK):

    client.messages.create(
        model="claude-sonnet-4-...",
        max_tokens=2048,
        thinking={"type": "enabled", "budget_tokens": 4096},
        messages=[...],
    )

The response contains ``thinking`` content blocks that you must not display
verbatim to end users. This recipe:

- enables extended thinking,
- separates visible text from internal reasoning,
- truncates the thinking summary for debugging without leaking it into the
  user-visible answer.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from common.client import CookbookClient
from common.logging import get_logger, setup_logging

logger = get_logger(__name__)


DEFAULT_PROBLEM = (
    "You are planning a week-long trip from Seoul to the US west coast. "
    "Departure on 2026-06-01, return on 2026-06-08. The traveler has a "
    "meeting in San Francisco on 2026-06-03 and wants to visit Seattle for "
    "two consecutive nights. Every flight leg must be a morning departure "
    "(before 12:00 local). Propose a 7-day itinerary with at most two "
    "domestic flights and calculate the minimum total flight count, "
    "including the international legs. Return your answer as bullet points."
)

SYSTEM_PROMPT = (
    "You are a careful planning assistant. Think step by step about "
    "constraints, enumerate candidate itineraries, and only then produce "
    "the final answer. Keep the visible answer concise and structured."
)


# ---------------------------------------------------------------------------
# Result shape
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ThinkingResult:
    visible_answer: str
    thinking_summary: str  # first 400 chars, for debugging — never show to users
    thinking_chars: int
    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int
    stop_reason: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "visible_answer": self.visible_answer,
            "thinking_summary": self.thinking_summary,
            "thinking_chars": self.thinking_chars,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_input_tokens": self.cache_read_input_tokens,
            "stop_reason": self.stop_reason,
        }


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------


def _block_attr(block: Any, name: str) -> Any:
    if isinstance(block, dict):
        return block.get(name)
    return getattr(block, name, None)


def _split_thinking_and_text(content: Any) -> tuple[str, str]:
    text_parts: list[str] = []
    thinking_parts: list[str] = []
    for block in content or []:
        btype = _block_attr(block, "type")
        if btype == "text":
            piece = _block_attr(block, "text") or ""
            text_parts.append(piece)
        elif btype in {"thinking", "redacted_thinking"}:
            piece = _block_attr(block, "thinking") or _block_attr(block, "text") or ""
            thinking_parts.append(piece)
    return "".join(text_parts), "".join(thinking_parts)


def solve_with_thinking(
    problem: str,
    *,
    client: CookbookClient,
    thinking_budget_tokens: int = 4096,
    max_tokens: int = 2048,
) -> ThinkingResult:
    response = client.create_message(
        messages=[{"role": "user", "content": problem}],
        system=SYSTEM_PROMPT,
        max_tokens=max_tokens,
        extra={
            "thinking": {
                "type": "enabled",
                "budget_tokens": thinking_budget_tokens,
            }
        },
    )
    raw_content = response.raw.content if response.raw else []
    visible, thinking = _split_thinking_and_text(raw_content)
    summary = thinking[:400]
    return ThinkingResult(
        visible_answer=visible,
        thinking_summary=summary,
        thinking_chars=len(thinking),
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        cache_read_input_tokens=response.cache_read_input_tokens,
        stop_reason=response.stop_reason,
    )


def _cli() -> int:
    parser = argparse.ArgumentParser(description="Recipe 07 — extended thinking")
    parser.add_argument("--problem", default=DEFAULT_PROBLEM)
    parser.add_argument("--budget", type=int, default=4096)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    setup_logging()
    client = CookbookClient()
    result = solve_with_thinking(
        args.problem,
        client=client,
        thinking_budget_tokens=args.budget,
    )
    rendered = json.dumps(result.as_dict(), indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
