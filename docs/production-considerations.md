# Production considerations

This cookbook is production-minded. The notes below capture decisions a team
should make before shipping any of the recipes to real users.

## Rate limits and retries

Anthropic enforces per-organization limits on requests-per-minute (RPM) and
tokens-per-minute (TPM). The defaults vary by tier. When either limit trips,
the API returns HTTP 429 with an `anthropic-ratelimit-*` header.

- The shipped `CookbookClient` retries transient errors (429, 5xx,
  connection/timeout) with bounded exponential backoff. See
  `common/client.py::_is_transient_error`.
- For high-throughput workloads, combine client-side token-bucket limiting
  with the Message Batches API (Recipe 06) for the offline portion of the
  load. Batches are 50% cheaper and skip the synchronous rate-limit lane.

## Cost controls

- Every request through `CookbookClient` writes to a `UsageLedger`. At the
  end of a run, `client.ledger.summary()` returns tokens and dollars. Log
  this in every recipe.
- Set per-run and per-user budgets. In `run_agent` (Recipe 02) we cap
  iterations; in production, also cap `client.ledger.cost_usd`.
- Prompt caching (Recipe 05) is the biggest single-request cost lever for
  long, stable prefixes. Measure `cache_read_input_tokens` to confirm it
  is landing before claiming the savings in a dashboard.

## Error handling

- **Transient vs. fatal.** 429/5xx/connection errors retry. 4xx errors
  (except 408/409) do not — they indicate a real bug you must fix.
- **Tool errors.** When a tool handler raises, the cookbook catches and
  returns a `tool_result` with `is_error=true`. Claude is usually good at
  self-correcting in the next turn. Set a hard iteration cap so a broken
  tool doesn't burn an entire budget.
- **Malformed outputs.** Recipe 04 demonstrates the `ok: bool` wrapper
  around all structured outputs; prefer this shape to raising exceptions
  because it keeps the pipeline composable.

## Observability

- Every recipe uses `common.logging.get_logger` which emits JSON lines. Ship
  those logs to your aggregator; key fields: `model`, `input_tokens`,
  `output_tokens`, `stop_reason`, `cache_read_input_tokens`, `cost_usd`.
- Add a per-user or per-session id by passing `extra={"metadata": {...}}`
  to `create_message`. The SDK forwards it to the API, which means
  Anthropic's request logs can correlate by the same id.

## Security

- Never commit `.env`. The `.gitignore` already refuses it, but verify in
  code review that no key accidentally lands in a fixture or test file.
- Tool handlers are a foot-gun: Claude can supply arbitrary argument
  values. Validate every input with Pydantic (see Recipes 01, 02, 08) and
  avoid shelling out with user-supplied strings.
- For RAG (Recipe 03), add a tenant identifier to every retrieved
  document's metadata and filter before handing passages to Claude. The
  model does not know your row-level security rules.

## Model pinning and upgrades

- Pin a specific model id in production. The cookbook defaults to
  `claude-sonnet-4-20250514`; override via the `CLAUDE_MODEL` env var.
- When you change model ids, run the Recipe 10 suite against a baseline
  captured on the old model. Treat unexpected regressions as blockers.

## Five-bullet summary

- Retry transient errors only; never retry 4xx.
- Log usage per request; roll up per recipe.
- Cache large stable prefixes and measure the cache read bytes.
- Validate every tool argument with Pydantic.
- Guard changes with Recipe 10 before they hit production.
