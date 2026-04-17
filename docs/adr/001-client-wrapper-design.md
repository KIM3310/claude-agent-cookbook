# ADR 001: Client Wrapper Design

- **Status**: Accepted
- **Date**: 2026-04-17

## Context

Every recipe in this cookbook needs to call the Anthropic API. Three options:

1. Each recipe instantiates `Anthropic()` directly.
2. A thin shared factory function returning `Anthropic()`.
3. A full wrapper class that adds retry, token counting, cost estimation, and structured logging.

## Decision

Adopt option 3. Build `common/client.py` as a `CookbookClient` class that wraps `anthropic.Anthropic`. All recipes use it; no recipe imports `anthropic` directly.

## Consequences

### Positive

- **Testability**: recipes are tested with a mocked `CookbookClient`, not with `unittest.mock.patch("anthropic.Anthropic")` across each test file. One patch point; cleaner tests.
- **Observability**: every call is logged with request_id, model, token counts, cost. Recipes don't duplicate logging code.
- **Retry in one place**: rate-limit and transient-error handling lives in `CookbookClient.send()`. Recipes assume success or raise.
- **Cost cap**: `CookbookClient` can refuse calls if a configured budget is exceeded in the current session. Useful for demos and CI.
- **Migration path**: if `anthropic` SDK breaking changes ship, we update one class, not ten recipes.

### Negative

- **Abstraction cost**: readers must understand `CookbookClient` before they can read recipe code. We mitigate this with a short "how to read the recipes" section in the root README.
- **Divergence from Anthropic's own cookbook style**: Anthropic's cookbook uses `Anthropic()` directly, for clarity. We optimize for production-shape code.
- **Surface area**: every new Anthropic feature (batch API, Files API, etc.) needs a pass-through on `CookbookClient`.

### Mitigations

- Keep `CookbookClient` a thin shell. No feature lives in the wrapper unless it's shared by 2+ recipes.
- Document every new `CookbookClient` method with a reference to the underlying Anthropic SDK method.
- Provide a `CookbookClient.raw` attribute exposing the underlying `Anthropic()` for escape-hatch usage.

## Alternatives considered

### Option 1 — direct instantiation in each recipe

Rejected. Ten recipes × boilerplate = copy-paste drift within weeks. Every retry policy disagreement becomes a bug.

### Option 2 — thin factory function

Rejected. Solves 20% of the problem (consistent instantiation) but not the other 80% (logging, retry, cost tracking).

### Option 4 — adopt a third-party framework (LangChain, LlamaIndex)

Rejected. Framework overhead outweighs benefits for a 10-recipe cookbook. Wrappers force readers to learn our choices plus the framework's. This cookbook competes with Anthropic's own docs on clarity; dropping a heavy framework adds friction.

## Implementation details

`CookbookClient.send()` is the single entry point. Signature:

```python
def send(
    self,
    *,
    model: str,
    messages: list[MessageParam],
    max_tokens: int = 1024,
    system: str | list[dict] | None = None,
    tools: list[dict] | None = None,
    temperature: float = 0.0,
    thinking: dict | None = None,
    cache_system: bool = False,
    stream: bool = False,
    request_id: str | None = None,
) -> MessageResponse:
    ...
```

Observability hooks:
- Before call: log `{request_id, model, input_token_estimate}`.
- After call: log `{request_id, latency_ms, input_tokens, output_tokens, cache_read_tokens, cost_usd}`.

Retry policy:
- `RateLimitError`: exponential backoff, max 5 attempts.
- `APIStatusError` with 5xx: exponential backoff, max 3 attempts.
- `APIStatusError` with 4xx: fail fast.

Cost estimation:
- `PRICING` table in `common/client.py` keyed by model id.
- Track session-level spend in `CookbookClient.session_cost`.
- Optional `budget_usd` parameter; raising `BudgetExceededError` if breached.

## References

- `common/client.py` — implementation.
- `common/test_client.py` — tests verifying retry and logging behavior.
- [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python)
