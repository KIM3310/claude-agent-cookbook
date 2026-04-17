"""Recipe 05: prompt caching for large, stable system prompts.

When the same multi-kilobyte system prompt prefixes many requests, we can
mark it cacheable with ``cache_control: {"type": "ephemeral"}``. Anthropic
charges a one-time write premium and then serves subsequent reads at a deep
discount (~10% of the normal input token price) until the cache expires.

This recipe:

- builds a large, stable "policy manual" as a cacheable system prefix,
- sends two requests back-to-back with identical cacheable prefixes,
- measures the ``cache_read_input_tokens`` and ``cache_creation_input_tokens``
  fields of ``response.usage`` to confirm the cache hit,
- reports the observed savings in tokens and dollars.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from common.client import CookbookClient, estimate_cost_usd
from common.logging import get_logger, setup_logging

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Cacheable system prompt assembly
# ---------------------------------------------------------------------------


POLICY_PREAMBLE = (
    "You are 'Atlas', the internal policy assistant for Frontier Labs. "
    "You answer questions using the Frontier Labs Employee Handbook below. "
    "Cite sections as [section:NN] inline. Never reveal internal ticket "
    "numbers. Keep responses under 120 words."
)


def _generate_handbook(sections: int = 40, lines_per_section: int = 8) -> str:
    """Build a deterministic, ~cacheable handbook body.

    The text is long enough to comfortably exceed the smallest supported
    cache breakpoint so the feature is actually exercised in production. The
    exact minimum token count depends on the model; see Anthropic's docs for
    current thresholds.
    """
    out: list[str] = ["# Frontier Labs Employee Handbook", ""]
    for i in range(1, sections + 1):
        out.append(f"## Section {i:02d}")
        for line_num in range(1, lines_per_section + 1):
            out.append(
                f"Provision {i:02d}.{line_num}: employees should follow process "
                f"{i:02d}.{line_num} when handling routine operational tasks. "
                "This includes appropriate documentation, manager sign-off, and "
                "retention of records for the period mandated by policy."
            )
        out.append("")
    return "\n".join(out)


HANDBOOK_BODY = _generate_handbook()


def build_cacheable_system() -> list[dict[str, Any]]:
    """Return the system-prompt payload with an ephemeral cache breakpoint.

    Anthropic's API accepts ``system`` as a list of typed blocks. Attaching
    ``cache_control`` to the large handbook block tells the service to cache
    the shared prefix. The short preamble sits *before* the cached block
    because cache breakpoints cache everything up to and including the
    annotated block, so ordering determines what becomes reusable.
    """

    return [
        {"type": "text", "text": POLICY_PREAMBLE},
        {
            "type": "text",
            "text": HANDBOOK_BODY,
            "cache_control": {"type": "ephemeral"},
        },
    ]


# ---------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class CacheMeasurement:
    user_prompt: str
    text: str
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int
    cache_read_input_tokens: int
    cost_usd: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "user_prompt": self.user_prompt,
            "text": self.text,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_creation_input_tokens": self.cache_creation_input_tokens,
            "cache_read_input_tokens": self.cache_read_input_tokens,
            "cost_usd": self.cost_usd,
        }


def measure_once(
    client: CookbookClient,
    *,
    user_prompt: str,
    system: list[dict[str, Any]] | None = None,
) -> CacheMeasurement:
    response = client.create_message(
        messages=[{"role": "user", "content": user_prompt}],
        system=system or build_cacheable_system(),
        max_tokens=256,
        temperature=0.0,
    )
    return CacheMeasurement(
        user_prompt=user_prompt,
        text=response.text,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        cache_creation_input_tokens=response.cache_creation_input_tokens,
        cache_read_input_tokens=response.cache_read_input_tokens,
        cost_usd=estimate_cost_usd(
            model=response.model or client.default_model,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            cache_read_input_tokens=response.cache_read_input_tokens,
            cache_creation_input_tokens=response.cache_creation_input_tokens,
        ),
    )


def compare_runs(
    client: CookbookClient,
    *,
    prompts: list[str] | None = None,
) -> dict[str, Any]:
    """Run N requests that share the same cacheable system prefix and report savings."""

    prompts = prompts or [
        "Summarize Section 01 in one sentence.",
        "What does Section 02 require for record retention?",
        "If an employee forgets manager sign-off, which section applies?",
    ]
    system = build_cacheable_system()
    measurements = [
        measure_once(client, user_prompt=p, system=system) for p in prompts
    ]
    first, *rest = measurements
    read_total = sum(m.cache_read_input_tokens for m in rest)
    full_prefix_tokens = first.cache_creation_input_tokens or first.input_tokens
    cached_percentage = (
        (read_total / (full_prefix_tokens * len(rest))) if rest and full_prefix_tokens else 0.0
    )
    total_cost = sum(m.cost_usd for m in measurements)
    return {
        "runs": [m.as_dict() for m in measurements],
        "summary": {
            "total_requests": len(measurements),
            "cache_write_tokens": first.cache_creation_input_tokens,
            "cache_read_tokens_total": read_total,
            "estimated_prefix_reuse_pct": round(cached_percentage * 100, 2),
            "total_cost_usd": round(total_cost, 6),
        },
    }


def _cli() -> int:
    parser = argparse.ArgumentParser(description="Recipe 05 — prompt caching")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    setup_logging()
    client = CookbookClient()
    report = compare_runs(client)
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
