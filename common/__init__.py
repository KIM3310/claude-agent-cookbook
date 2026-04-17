"""Shared infrastructure for the Claude Agent Cookbook.

This package provides a small, curated surface area that every recipe uses:

- :mod:`common.client` — a thin wrapper around the Anthropic SDK with retries,
  cost estimation, and structured telemetry hooks.
- :mod:`common.eval` — a rubric-driven evaluation framework with regression
  detection.
- :mod:`common.tools` — Pydantic tool definitions shared across multi-turn
  recipes.
- :mod:`common.logging` — structured logging setup usable from every recipe.
- :mod:`common.types` — shared typed data structures.

Nothing here performs real network I/O at import time. Recipes are expected to
construct a :class:`~common.client.CookbookClient` explicitly.
"""

from common.client import CookbookClient, UsageLedger, estimate_cost_usd
from common.eval import (
    EvalCase,
    EvalResult,
    EvalSuite,
    RegressionReport,
    Rubric,
    run_suite,
)
from common.logging import get_logger, setup_logging
from common.tools import ToolDefinition, ToolRegistry
from common.types import CompletionResult, Message, RecipeContext

__all__ = [
    # client
    "CookbookClient",
    "UsageLedger",
    "estimate_cost_usd",
    # eval
    "EvalCase",
    "EvalResult",
    "EvalSuite",
    "RegressionReport",
    "Rubric",
    "run_suite",
    # logging
    "get_logger",
    "setup_logging",
    # tools
    "ToolDefinition",
    "ToolRegistry",
    # types
    "CompletionResult",
    "Message",
    "RecipeContext",
]
