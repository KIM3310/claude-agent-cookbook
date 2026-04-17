"""Shared type definitions used across recipes.

Keeping these in one module keeps recipe code short and makes the public surface
of the cookbook obvious. Where a concept has a Pydantic equivalent in the
Anthropic SDK we mirror its field names so mental models stay aligned.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict

Role = Literal["user", "assistant", "system", "tool"]


class Message(TypedDict, total=False):
    """A single chat turn as the Anthropic SDK expects it.

    ``content`` is deliberately ``Any`` because Anthropic messages can be either
    a plain string or a list of typed content blocks (text, tool_use,
    tool_result, image). The SDK performs the final validation.
    """

    role: Role
    content: Any


@dataclass(slots=True)
class CompletionResult:
    """A normalized completion result returned from :class:`CookbookClient`.

    We intentionally keep this tiny — recipes that need SDK-native objects can
    access ``raw``. This dataclass exists so that cookbook-level code (eval
    harness, logging, recipe plumbing) doesn't need to know about SDK internals.
    """

    text: str
    stop_reason: str | None
    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    model: str = ""
    raw: Any = None

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(slots=True)
class RecipeContext:
    """Runtime context passed into every recipe entrypoint.

    Recipes are expected to accept a ``RecipeContext`` rather than reading
    environment variables directly. That makes them trivially testable — the
    test suite can inject a fake client, a fake logger, and a deterministic
    artifact directory without touching global state.
    """

    client: Any  # forward-typed to avoid circular import; see common.client
    model: str
    artifact_dir: str
    extra: dict[str, Any] = field(default_factory=dict)
