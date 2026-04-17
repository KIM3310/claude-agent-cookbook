"""Thin wrapper around the Anthropic SDK.

The goal is not to abstract the SDK away — recipes still receive the raw
response through :attr:`CompletionResult.raw` — but to centralize the
concerns every production caller repeats:

- retries with exponential backoff on transient failures
- a usage ledger so we can measure cache hits, token counts, and cost
- a structured log line per request
- deterministic cost estimation based on a lookup table of published prices

The wrapper lazily constructs the underlying ``anthropic.Anthropic`` client so
tests can inject a fake via :meth:`CookbookClient.with_raw_client`.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from common.logging import get_logger
from common.types import CompletionResult

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------

# USD per million tokens. Update when Anthropic revises pricing. These
# defaults reflect published Claude Sonnet tier pricing; recipes that target
# a different tier should call :func:`estimate_cost_usd` with explicit rates.
DEFAULT_PRICE_TABLE: dict[str, tuple[float, float, float, float]] = {
    # model_id -> (input_per_mtok, output_per_mtok, cache_write_per_mtok, cache_read_per_mtok)
    "claude-sonnet-4-20250514": (3.00, 15.00, 3.75, 0.30),
    "claude-3-5-sonnet-20241022": (3.00, 15.00, 3.75, 0.30),
    "claude-3-5-haiku-20241022": (0.80, 4.00, 1.00, 0.08),
    "claude-3-opus-20240229": (15.00, 75.00, 18.75, 1.50),
}


def estimate_cost_usd(
    *,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_input_tokens: int = 0,
    cache_creation_input_tokens: int = 0,
    price_table: dict[str, tuple[float, float, float, float]] | None = None,
) -> float:
    """Estimate USD cost for a request using a published price table.

    Missing models fall back to the Sonnet-4 tier so we never crash when
    pricing hasn't been catalogued; the caller gets a best-effort number.
    """

    table = price_table or DEFAULT_PRICE_TABLE
    rates = table.get(model) or table["claude-sonnet-4-20250514"]
    in_rate, out_rate, cache_write_rate, cache_read_rate = rates

    uncached_input = max(input_tokens - cache_read_input_tokens - cache_creation_input_tokens, 0)
    cost = (
        (uncached_input / 1_000_000) * in_rate
        + (output_tokens / 1_000_000) * out_rate
        + (cache_creation_input_tokens / 1_000_000) * cache_write_rate
        + (cache_read_input_tokens / 1_000_000) * cache_read_rate
    )
    return round(cost, 6)


# ---------------------------------------------------------------------------
# Usage ledger
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class UsageLedger:
    """Accumulates per-recipe usage so we can report totals."""

    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cost_usd: float = 0.0
    entries: list[dict[str, Any]] = field(default_factory=list)

    def record(self, result: CompletionResult, *, model: str) -> None:
        self.requests += 1
        self.input_tokens += result.input_tokens
        self.output_tokens += result.output_tokens
        self.cache_read_input_tokens += result.cache_read_input_tokens
        self.cache_creation_input_tokens += result.cache_creation_input_tokens
        cost = estimate_cost_usd(
            model=model,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cache_read_input_tokens=result.cache_read_input_tokens,
            cache_creation_input_tokens=result.cache_creation_input_tokens,
        )
        self.cost_usd = round(self.cost_usd + cost, 6)
        self.entries.append(
            {
                "model": model,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "cache_read_input_tokens": result.cache_read_input_tokens,
                "cache_creation_input_tokens": result.cache_creation_input_tokens,
                "cost_usd": cost,
            }
        )

    def summary(self) -> dict[str, Any]:
        return {
            "requests": self.requests,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_input_tokens": self.cache_read_input_tokens,
            "cache_creation_input_tokens": self.cache_creation_input_tokens,
            "cost_usd": round(self.cost_usd, 6),
        }


# ---------------------------------------------------------------------------
# Retry policy
# ---------------------------------------------------------------------------


_TRANSIENT_STATUS_CODES = frozenset({408, 409, 429, 500, 502, 503, 504})


def _is_transient_error(exc: BaseException) -> bool:
    """Return True if ``exc`` looks like a transient Anthropic API error."""
    status = getattr(exc, "status_code", None)
    if isinstance(status, int) and status in _TRANSIENT_STATUS_CODES:
        return True
    name = exc.__class__.__name__
    return name in {
        "APIConnectionError",
        "APITimeoutError",
        "RateLimitError",
        "InternalServerError",
        "ServiceUnavailableError",
    }


# ---------------------------------------------------------------------------
# Client wrapper
# ---------------------------------------------------------------------------


class CookbookClient:
    """Production-minded wrapper around ``anthropic.Anthropic``.

    Responsibilities:

    - construct the underlying SDK client lazily
    - apply bounded retries on transient errors
    - normalize responses into :class:`CompletionResult`
    - track usage in an attached :class:`UsageLedger`
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        default_model: str | None = None,
        max_retries: int | None = None,
        timeout_seconds: float | None = None,
        raw_client: Any = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.default_model = default_model or os.environ.get(
            "CLAUDE_MODEL", "claude-sonnet-4-20250514"
        )
        self.max_retries = (
            max_retries
            if max_retries is not None
            else int(os.environ.get("CLAUDE_MAX_RETRIES", "3"))
        )
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else float(os.environ.get("CLAUDE_TIMEOUT_SECONDS", "60"))
        )
        self._raw_client = raw_client
        self.ledger = UsageLedger()

    # ---- client construction -------------------------------------------------
    @classmethod
    def with_raw_client(cls, raw_client: Any, *, default_model: str = "test-model") -> CookbookClient:
        """Build a client around an already-constructed SDK object — used in tests."""
        return cls(raw_client=raw_client, default_model=default_model, max_retries=0)

    @property
    def raw(self) -> Any:
        """Return the underlying Anthropic SDK client, constructing it on demand."""
        if self._raw_client is None:
            try:
                import anthropic  # noqa: WPS433 — deferred import by design
            except ImportError as exc:  # pragma: no cover — exercised in install docs
                raise RuntimeError(
                    "The 'anthropic' package is not installed. Run `pip install -r requirements.txt`."
                ) from exc
            if not self._api_key:
                raise RuntimeError(
                    "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in."
                )
            self._raw_client = anthropic.Anthropic(
                api_key=self._api_key,
                timeout=self.timeout_seconds,
            )
        return self._raw_client

    # ---- core entrypoint -----------------------------------------------------
    def create_message(
        self,
        *,
        messages: list[dict[str, Any]],
        system: str | Iterable[dict[str, Any]] | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: dict[str, Any] | None = None,
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float | None = None,
        extra: dict[str, Any] | None = None,
    ) -> CompletionResult:
        """Send a single non-streaming request.

        Extra kwargs (``extra``) are forwarded verbatim to the SDK so new
        Anthropic features can be used without updating this wrapper.
        """

        payload: dict[str, Any] = {
            "model": model or self.default_model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system is not None:
            payload["system"] = system
        if tools:
            payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        if temperature is not None:
            payload["temperature"] = temperature
        if extra:
            payload.update(extra)

        response = self._with_retries(lambda: self.raw.messages.create(**payload))
        result = _normalize(response, requested_model=payload["model"])
        self.ledger.record(result, model=payload["model"])
        logger.info(
            "claude.request",
            extra={
                "model": payload["model"],
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "cache_read_input_tokens": result.cache_read_input_tokens,
                "cache_creation_input_tokens": result.cache_creation_input_tokens,
                "stop_reason": result.stop_reason,
            },
        )
        return result

    # ---- retry loop ----------------------------------------------------------
    def _with_retries(self, call: Any) -> Any:
        last_error: BaseException | None = None
        attempts = self.max_retries + 1
        for attempt in range(1, attempts + 1):
            try:
                return call()
            except Exception as exc:  # noqa: BLE001 — we classify below
                if attempt == attempts or not _is_transient_error(exc):
                    raise
                backoff = min(2.0 ** (attempt - 1), 8.0)
                logger.warning(
                    "claude.retry",
                    extra={
                        "attempt": attempt,
                        "max_attempts": attempts,
                        "backoff_seconds": backoff,
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    },
                )
                last_error = exc
                time.sleep(backoff)
        # Defensive; the loop above must either return or re-raise.
        raise RuntimeError("retry loop exited unexpectedly") from last_error


# ---------------------------------------------------------------------------
# Response normalization
# ---------------------------------------------------------------------------


def _text_from_blocks(blocks: Any) -> str:
    """Concatenate text blocks from an Anthropic message response."""
    if isinstance(blocks, str):
        return blocks
    parts: list[str] = []
    for block in blocks or []:
        block_type = _get(block, "type")
        if block_type == "text":
            text = _get(block, "text")
            if isinstance(text, str):
                parts.append(text)
    return "".join(parts)


def _get(obj: Any, name: str, default: Any = None) -> Any:
    """Read an attribute from SDK pydantic objects or plain dict fixtures."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _normalize(response: Any, *, requested_model: str) -> CompletionResult:
    usage = _get(response, "usage") or {}
    content_blocks = _get(response, "content") or []
    return CompletionResult(
        text=_text_from_blocks(content_blocks),
        stop_reason=_get(response, "stop_reason"),
        input_tokens=int(_get(usage, "input_tokens") or 0),
        output_tokens=int(_get(usage, "output_tokens") or 0),
        cache_read_input_tokens=int(_get(usage, "cache_read_input_tokens") or 0),
        cache_creation_input_tokens=int(_get(usage, "cache_creation_input_tokens") or 0),
        model=_get(response, "model") or requested_model,
        raw=response,
    )
