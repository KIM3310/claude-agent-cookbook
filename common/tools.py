"""Tool definitions for Claude's tool-use API.

Claude's ``tools`` parameter accepts JSON-Schema style definitions. Writing
those by hand is error-prone, so we let recipe authors define tools with
Pydantic v2 models and derive the schema automatically.

Example::

    from pydantic import BaseModel, Field
    from common.tools import ToolDefinition, ToolRegistry

    class GetWeatherArgs(BaseModel):
        city: str = Field(..., description="City name, e.g. 'Seoul'")
        unit: str = Field("celsius", description="celsius or fahrenheit")

    def get_weather(args: GetWeatherArgs) -> dict[str, str]:
        return {"temperature": "22", "conditions": "clear"}

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="get_weather",
            description="Look up current weather for a city.",
            args_model=GetWeatherArgs,
            handler=get_weather,
        )
    )
    anthropic_tools = registry.to_anthropic()
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError


@dataclass(slots=True)
class ToolDefinition:
    """A single tool Claude can call.

    - ``name`` is what Claude sees and emits.
    - ``description`` is the prompt-visible description — keep it precise;
      imprecise descriptions lead to wrong tool selection.
    - ``args_model`` is a Pydantic v2 model. Its schema (minus the extraneous
      ``title`` fields Claude doesn't need) becomes ``input_schema``.
    - ``handler`` is the local Python function invoked when Claude calls the
      tool. It accepts the validated args model and returns a JSON-serializable
      result.
    """

    name: str
    description: str
    args_model: type[BaseModel]
    handler: Callable[[Any], Any]

    def input_schema(self) -> dict[str, Any]:
        """Return the JSON schema Claude expects in the ``tools`` array."""
        schema = self.args_model.model_json_schema()
        schema.pop("title", None)
        for prop in schema.get("properties", {}).values():
            prop.pop("title", None)
        return schema

    def to_anthropic(self) -> dict[str, Any]:
        """Serialize to the exact shape ``client.messages.create(tools=...)`` wants."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema(),
        }

    def invoke(self, raw_input: dict[str, Any]) -> Any:
        """Validate ``raw_input`` against :attr:`args_model`, then run the handler."""
        try:
            parsed = self.args_model(**raw_input)
        except ValidationError as exc:
            raise ToolArgumentError(self.name, raw_input, exc) from exc
        return self.handler(parsed)


class ToolArgumentError(ValueError):
    """Raised when Claude supplies arguments that fail Pydantic validation.

    Caught by the cookbook tool loop, which returns a tool_result with
    ``is_error=True`` so Claude can self-correct on the next turn.
    """

    def __init__(self, tool_name: str, payload: dict[str, Any], cause: ValidationError) -> None:
        self.tool_name = tool_name
        self.payload = payload
        self.cause = cause
        super().__init__(f"Invalid arguments for tool '{tool_name}': {cause}")


class ToolRegistry:
    """A small, ordered registry of tools.

    Ordering is preserved so that the schema you ship to Claude mirrors the
    order in which you registered the tools — useful for deterministic tests.
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")
        self._tools[tool.name] = tool

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def get(self, name: str) -> ToolDefinition:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"Unknown tool '{name}'. Registered: {self.names()}") from exc

    def to_anthropic(self) -> list[dict[str, Any]]:
        """Serialize the whole registry for the Anthropic ``tools`` parameter."""
        return [t.to_anthropic() for t in self._tools.values()]

    def invoke(self, name: str, raw_input: dict[str, Any]) -> Any:
        return self.get(name).invoke(raw_input)
