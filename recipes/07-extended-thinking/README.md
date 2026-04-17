# Recipe 07: Extended thinking for hard problems

## Problem

You have a planning, math, or deep-analysis task where the first answer
Claude produces is often wrong. Extended thinking lets Claude spend a
dedicated token budget on internal reasoning before the visible answer,
improving accuracy on constraint-heavy tasks.

## Claude features used

- **Extended thinking** via the `thinking` parameter:
  `{"type": "enabled", "budget_tokens": N}`.
- **`thinking` content blocks** in the response, separated from `text`
  blocks.
- Optional **`redacted_thinking`** blocks when the service determines
  portions of the reasoning must not be exposed.

## Pattern

```mermaid
sequenceDiagram
  participant U as User
  participant C as Claude
  U->>C: problem (thinking={enabled, budget=4096})
  C-->>C: internal deliberation (thinking blocks)
  C-->>U: response = [thinking blocks] + [text blocks]
  U->>U: split blocks; show only `text` to end user
```

## Implementation

- `_split_thinking_and_text` — walks the response content and returns
  `(visible, thinking)` so callers never confuse the two.
- `solve_with_thinking` — single entry point that enables extended thinking,
  captures usage, and returns a `ThinkingResult` dataclass with the visible
  answer, a truncated `thinking_summary` for debugging, and `thinking_chars`
  so eval code can reason about reasoning effort.

## Running it

```bash
python recipes/07-extended-thinking/recipe.py --budget 4096
```

## Expected output

```json
{
  "visible_answer": "- 2026-06-01: Seoul ICN -> San Francisco SFO ...",
  "thinking_chars": 1847,
  "input_tokens": 380,
  "output_tokens": 920
}
```

Full payload in [`expected_output.json`](expected_output.json). The
`thinking_summary` field exists for developer inspection only and must not
be surfaced in user-facing UIs.

## Testing

`test_recipe.py` covers:

1. `_split_thinking_and_text` handles mixed `thinking` and `text` blocks.
2. `solve_with_thinking` forwards `thinking={type, budget_tokens}` to the
   SDK.
3. The visible answer never contains thinking text — the separation
   invariant holds.
4. Long thinking is truncated to a 400-char summary while `thinking_chars`
   reports the real length.
5. The no-thinking path: when the response omits thinking blocks entirely,
   the recipe still returns a useful `ThinkingResult`.

## When to use this

- Use for planning with multiple interacting constraints, algebra-heavy
  problems, code review where the pass/fail depends on subtle invariants.
- Use when your eval shows >5% accuracy lift from reasoning.
- Avoid for simple retrieval, classification, or conversational turns where
  the reasoning budget is wasted.
- Avoid for user-facing latency-sensitive paths; reasoning adds seconds.

## Extending

- **Budget sweeping.** Evaluate the same prompt at 1K / 4K / 16K budgets and
  pick the smallest budget that clears your accuracy bar. Wire the sweep
  into recipe 10's eval harness.
- **Tool use with thinking.** Extended thinking is compatible with tool use
  — Claude can reason about which tool to call. Combine recipes 02 and 07
  for planner-style agents.
- **Redacted thinking.** If your audit trail needs to verify Claude did
  reason (without storing the reasoning), hash the `thinking` block and
  persist only the hash.

## References

- [Anthropic: Extended thinking](https://docs.anthropic.com/en/docs/build-with-claude/extended-thinking)
- [Anthropic: Thinking block types](https://docs.anthropic.com/en/api/messages)
