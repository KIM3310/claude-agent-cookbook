"""Recipe 06: offline evaluation at scale with the Message Batches API.

The Message Batches endpoint accepts up to 10,000 independent prompts per
submission, runs them asynchronously within a 24-hour SLO, and charges at
roughly half the price of synchronous requests. It is the right surface for:

- offline eval sweeps over a gold set,
- bulk data labeling or synthetic data generation,
- overnight backfill jobs.

This recipe shows the full lifecycle:

1. Build a JSONL file of requests with stable ``custom_id`` values.
2. Submit the batch via ``client.messages.batches.create``.
3. Poll for completion with bounded retries.
4. Stream results, pairing each result back to its originating ``custom_id``.

The recipe is structured so tests can exercise every step without touching
the real API — a fake batch client is injected in tests.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from common.client import CookbookClient
from common.logging import get_logger, setup_logging

logger = get_logger(__name__)


BATCH_INPUT_PATH = Path(__file__).parent / "batch_input.jsonl"


# ---------------------------------------------------------------------------
# Input construction
# ---------------------------------------------------------------------------


def build_batch_requests(
    prompts: list[tuple[str, str]],
    *,
    model: str,
    system: str | None = None,
    max_tokens: int = 256,
) -> list[dict[str, Any]]:
    """Translate ``(custom_id, user_prompt)`` pairs into Batch API request envelopes."""
    requests: list[dict[str, Any]] = []
    for custom_id, prompt in prompts:
        params: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system is not None:
            params["system"] = system
        requests.append({"custom_id": custom_id, "params": params})
    return requests


def write_batch_jsonl(requests: list[dict[str, Any]], path: Path) -> Path:
    """Serialize batch requests to JSONL for persistence or reuse."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for entry in requests:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return path


def load_batch_jsonl(path: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            entries.append(json.loads(line))
    return entries


# ---------------------------------------------------------------------------
# Batch execution
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class BatchOutcome:
    batch_id: str
    status: str
    results: list[dict[str, Any]] = field(default_factory=list)
    polls: int = 0


def _get_batches_namespace(client: CookbookClient) -> Any:
    """Return the SDK's ``messages.batches`` namespace on the raw client."""
    try:
        return client.raw.messages.batches
    except AttributeError as exc:  # pragma: no cover — depends on SDK version
        raise RuntimeError(
            "This SDK version does not expose messages.batches. "
            "Upgrade the anthropic package."
        ) from exc


def submit_batch(
    client: CookbookClient,
    requests: list[dict[str, Any]],
) -> str:
    """Submit a batch and return its batch id."""
    batches = _get_batches_namespace(client)
    created = batches.create(requests=requests)
    batch_id = _attr(created, "id")
    if not isinstance(batch_id, str):
        raise RuntimeError(f"Batch API did not return an id; got {created!r}")
    logger.info("batch.submitted", extra={"batch_id": batch_id, "count": len(requests)})
    return batch_id


def poll_batch(
    client: CookbookClient,
    batch_id: str,
    *,
    interval_seconds: float = 5.0,
    max_polls: int = 360,  # 30 min at default interval
    sleep: Any = time.sleep,
) -> tuple[str, int]:
    """Poll until the batch is ``ended`` or ``failed``. Returns (status, polls)."""
    batches = _get_batches_namespace(client)
    polls = 0
    terminal = {"ended", "failed", "canceled", "expired"}
    while polls < max_polls:
        polls += 1
        batch = batches.retrieve(batch_id)
        status = _attr(batch, "processing_status") or _attr(batch, "status") or ""
        logger.info("batch.poll", extra={"batch_id": batch_id, "status": status, "poll": polls})
        if status in terminal:
            return status, polls
        sleep(interval_seconds)
    return "timed_out", polls


def iter_batch_results(
    client: CookbookClient,
    batch_id: str,
) -> list[dict[str, Any]]:
    """Collect per-request results into a list of dicts."""
    batches = _get_batches_namespace(client)
    entries = batches.results(batch_id)
    collected: list[dict[str, Any]] = []
    for entry in entries:
        custom_id = _attr(entry, "custom_id")
        result = _attr(entry, "result") or {}
        result_type = _attr(result, "type") or ""
        message = _attr(result, "message") or {}
        text = _first_text_block(_attr(message, "content"))
        collected.append(
            {
                "custom_id": custom_id,
                "result_type": result_type,
                "text": text,
                "raw": entry,
            }
        )
    return collected


def run_batch(
    client: CookbookClient,
    requests: list[dict[str, Any]],
    *,
    interval_seconds: float = 5.0,
    max_polls: int = 360,
    sleep: Any = time.sleep,
) -> BatchOutcome:
    batch_id = submit_batch(client, requests)
    status, polls = poll_batch(
        client,
        batch_id,
        interval_seconds=interval_seconds,
        max_polls=max_polls,
        sleep=sleep,
    )
    results = iter_batch_results(client, batch_id) if status == "ended" else []
    return BatchOutcome(batch_id=batch_id, status=status, results=results, polls=polls)


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _attr(obj: Any, name: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _first_text_block(content: Any) -> str:
    if isinstance(content, str):
        return content
    for block in content or []:
        if _attr(block, "type") == "text":
            text = _attr(block, "text")
            if isinstance(text, str):
                return text
    return ""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _default_prompts(n: int = 100) -> list[tuple[str, str]]:
    return [
        (f"eval-{i:04d}", f"Classify the sentiment of this sentence: 'sample text #{i}'.")
        for i in range(n)
    ]


def _cli() -> int:
    parser = argparse.ArgumentParser(description="Recipe 06 — Message Batches API")
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--input", type=Path, default=BATCH_INPUT_PATH)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    setup_logging()
    client = CookbookClient()
    prompts = _default_prompts(args.count)
    requests = build_batch_requests(
        prompts,
        model=client.default_model,
        system="You label sentiment as one of: positive, neutral, negative. Respond with one word.",
    )
    write_batch_jsonl(requests, args.input)
    outcome = run_batch(client, requests)
    payload = {
        "batch_id": outcome.batch_id,
        "status": outcome.status,
        "polls": outcome.polls,
        "result_count": len(outcome.results),
        "first_results": outcome.results[:5],
    }
    rendered = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
