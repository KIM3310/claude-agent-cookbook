"""Recipe 08: coordinator + specialist multi-agent pattern.

A single Claude session is often good enough. But some tasks are cleaner when
we split a coordinator (which plans and synthesizes) from specialists
(each with a tight persona and optimized prompt). This recipe implements
the pattern for a product-launch drafting task:

- **Coordinator** — decomposes the request into subtasks, calls specialists
  via a typed tool, synthesizes the final deliverable.
- **Research specialist** — extracts positioning notes from a brief.
- **Copywriter specialist** — produces user-facing copy.
- **Engineering specialist** — produces an implementation plan.

The coordinator sees specialists as three tools. That mapping is the key
insight: tools already carry schema, description, and a dispatch handler —
which is exactly what sub-agents need.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, Field

from common.client import CookbookClient
from common.logging import get_logger, setup_logging
from common.tools import ToolDefinition, ToolRegistry

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Specialist prompts
# ---------------------------------------------------------------------------


RESEARCH_SYSTEM = (
    "You are a product researcher. Given a launch brief, extract 3-5 crisp "
    "positioning notes in bullet form. Stay under 120 words."
)

COPY_SYSTEM = (
    "You are a product copywriter. Given a launch brief and positioning "
    "notes, draft a 2-paragraph landing-page intro. Warm, concrete, no "
    "marketing jargon."
)

ENGINEERING_SYSTEM = (
    "You are a senior engineer. Given a launch brief, outline the "
    "shipping plan as a numbered list: infrastructure, data, evaluation, "
    "rollout. Keep each line under 20 words."
)

COORDINATOR_SYSTEM = (
    "You are the launch coordinator. For the given brief:\n"
    "1. Call `research` once with the brief to get positioning notes.\n"
    "2. Call `copywriter` with the brief and the research notes.\n"
    "3. Call `engineer` with the brief.\n"
    "4. Synthesize a single markdown document with three sections: "
    "'## Positioning', '## Copy', '## Engineering plan'. Do not add "
    "sections that were not produced by specialists. Keep the final "
    "document under 500 words."
)


# ---------------------------------------------------------------------------
# Specialist argument schemas
# ---------------------------------------------------------------------------


class ResearchArgs(BaseModel):
    brief: str = Field(..., min_length=10, description="The full launch brief text.")


class CopyArgs(BaseModel):
    brief: str = Field(..., min_length=10)
    positioning_notes: str = Field(..., min_length=5)


class EngineeringArgs(BaseModel):
    brief: str = Field(..., min_length=10)


# ---------------------------------------------------------------------------
# Specialist callables
# ---------------------------------------------------------------------------


SpecialistFn = Callable[[Any], str]


def make_specialist(
    client: CookbookClient,
    *,
    system: str,
    max_tokens: int = 512,
) -> SpecialistFn:
    """Factory: a bound callable that asks Claude to play a specialist role."""

    def run(user_prompt: str) -> str:
        response = client.create_message(
            messages=[{"role": "user", "content": user_prompt}],
            system=system,
            max_tokens=max_tokens,
            temperature=0.2,
        )
        return response.text.strip()

    return run


# ---------------------------------------------------------------------------
# Coordinator loop
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class CoordinatorTrace:
    specialist: str
    input: dict[str, Any]
    output: str


@dataclass(slots=True)
class CoordinatorOutcome:
    final_document: str
    trace: list[CoordinatorTrace] = field(default_factory=list)
    iterations: int = 0


def _block_attr(block: Any, name: str) -> Any:
    if isinstance(block, dict):
        return block.get(name)
    return getattr(block, name, None)


def _extract_tool_use_blocks(content: Any) -> list[Any]:
    return [
        b
        for b in (content or [])
        if _block_attr(b, "type") == "tool_use"
    ]


def build_specialist_tools(
    *,
    research: SpecialistFn,
    copywriter: SpecialistFn,
    engineer: SpecialistFn,
) -> tuple[ToolRegistry, list[CoordinatorTrace]]:
    """Wrap specialist callables as tools and return (registry, shared trace list)."""

    trace: list[CoordinatorTrace] = []

    def _research(args: ResearchArgs) -> dict[str, Any]:
        output = research(f"Brief:\n{args.brief}\n\nProduce positioning notes.")
        trace.append(CoordinatorTrace("research", args.model_dump(), output))
        return {"notes": output}

    def _copy(args: CopyArgs) -> dict[str, Any]:
        output = copywriter(
            f"Brief:\n{args.brief}\n\nPositioning:\n{args.positioning_notes}\n\nDraft landing-page intro."
        )
        trace.append(CoordinatorTrace("copywriter", args.model_dump(), output))
        return {"copy": output}

    def _eng(args: EngineeringArgs) -> dict[str, Any]:
        output = engineer(f"Brief:\n{args.brief}\n\nOutline the shipping plan.")
        trace.append(CoordinatorTrace("engineer", args.model_dump(), output))
        return {"plan": output}

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="research",
            description="Extract 3-5 product positioning notes from the brief.",
            args_model=ResearchArgs,
            handler=_research,
        )
    )
    registry.register(
        ToolDefinition(
            name="copywriter",
            description="Draft a 2-paragraph landing-page intro using the brief and positioning notes.",
            args_model=CopyArgs,
            handler=_copy,
        )
    )
    registry.register(
        ToolDefinition(
            name="engineer",
            description="Outline a numbered shipping plan from the brief.",
            args_model=EngineeringArgs,
            handler=_eng,
        )
    )
    return registry, trace


def coordinate(
    brief: str,
    *,
    client: CookbookClient,
    registry: ToolRegistry,
    trace: list[CoordinatorTrace],
    max_iterations: int = 6,
) -> CoordinatorOutcome:
    messages: list[dict[str, Any]] = [{"role": "user", "content": brief}]
    for iteration in range(1, max_iterations + 1):
        response = client.create_message(
            messages=messages,
            system=COORDINATOR_SYSTEM,
            tools=registry.to_anthropic(),
            max_tokens=1536,
        )
        if response.stop_reason != "tool_use":
            return CoordinatorOutcome(
                final_document=response.text,
                trace=list(trace),
                iterations=iteration,
            )
        raw_content = response.raw.content if response.raw else []
        tool_uses = _extract_tool_use_blocks(raw_content)
        results: list[dict[str, Any]] = []
        for block in tool_uses:
            output = registry.invoke(
                _block_attr(block, "name"),
                _block_attr(block, "input") or {},
            )
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": _block_attr(block, "id"),
                    "content": json.dumps(output),
                }
            )
        messages.append({"role": "assistant", "content": raw_content})
        messages.append({"role": "user", "content": results})

    return CoordinatorOutcome(
        final_document="Coordinator exceeded its iteration budget.",
        trace=list(trace),
        iterations=max_iterations,
    )


def run_launch(brief: str, *, client: CookbookClient) -> CoordinatorOutcome:
    registry, trace = build_specialist_tools(
        research=make_specialist(client, system=RESEARCH_SYSTEM),
        copywriter=make_specialist(client, system=COPY_SYSTEM),
        engineer=make_specialist(client, system=ENGINEERING_SYSTEM),
    )
    return coordinate(brief, client=client, registry=registry, trace=trace)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


DEFAULT_BRIEF = (
    "Atlas v2 is an internal policy assistant for Frontier Labs. It answers "
    "HR and procurement questions with citations from the employee "
    "handbook, respecting per-region policy variants. Launching in Seoul "
    "and Singapore offices first. Primary users: managers and finance ops."
)


def _cli() -> int:
    parser = argparse.ArgumentParser(description="Recipe 08 — coordinator + specialists")
    parser.add_argument("--brief", default=DEFAULT_BRIEF)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    setup_logging()
    client = CookbookClient()
    outcome = run_launch(args.brief, client=client)
    payload = {
        "iterations": outcome.iterations,
        "final_document": outcome.final_document,
        "trace": [
            {"specialist": t.specialist, "input_keys": list(t.input.keys()), "output_chars": len(t.output)}
            for t in outcome.trace
        ],
        "usage": client.ledger.summary(),
    }
    rendered = json.dumps(payload, indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
