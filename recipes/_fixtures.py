"""Shared test fixtures for recipe unit tests.

We build small, explicit fake objects that duck-type the Anthropic SDK
response shape. Keeping these in one module avoids duplicating the shape in
every recipe's test file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeTextBlock:
    text: str
    type: str = "text"


@dataclass
class FakeToolUseBlock:
    id_: str
    name: str
    input_: dict[str, Any]
    type: str = "tool_use"

    @property
    def id(self) -> str:  # noqa: A003 — matches SDK attribute
        return self.id_

    @property
    def input(self) -> dict[str, Any]:  # noqa: A003 — matches SDK attribute
        return self.input_


@dataclass
class FakeThinkingBlock:
    thinking: str
    type: str = "thinking"


@dataclass
class FakeUsage:
    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass
class FakeResponse:
    content: list[Any]
    usage: FakeUsage
    stop_reason: str = "end_turn"
    model: str = "claude-sonnet-4-20250514"
    id: str = "msg_fake"
    role: str = "assistant"
    type: str = "message"
    stop_sequence: str | None = None


def build_response(
    *,
    content: list[Any],
    usage: FakeUsage,
    stop_reason: str = "end_turn",
    model: str = "claude-sonnet-4-20250514",
) -> FakeResponse:
    return FakeResponse(content=content, usage=usage, stop_reason=stop_reason, model=model)


@dataclass
class FakeStreamEvent:
    """Minimal streaming event for recipe 09 tests."""

    type: str
    delta: dict[str, Any] = field(default_factory=dict)
    content_block: dict[str, Any] = field(default_factory=dict)
    index: int = 0
    message: dict[str, Any] = field(default_factory=dict)
    usage: dict[str, Any] = field(default_factory=dict)
