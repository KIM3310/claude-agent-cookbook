# Prompts used in recipe 07

## System prompt

```text
You are a careful planning assistant. Think step by step about constraints,
enumerate candidate itineraries, and only then produce the final answer.
Keep the visible answer concise and structured.
```

### Rationale

- **"Think step by step ... only then produce the final answer."** With
  extended thinking enabled, this instruction encourages Claude to use its
  thinking budget for exploration before committing to a visible plan.
- **Separation of concerns.** The instruction sets two tones: exploratory in
  the thinking block, concise in the user-visible answer. The recipe then
  enforces the separation in code: `visible_answer` is always the `text`
  blocks, `thinking_summary` is the `thinking` blocks (truncated, and
  intended for debugging only).

## Extended thinking parameter

Passed through the SDK as:

```python
client.messages.create(
    ...,
    thinking={"type": "enabled", "budget_tokens": 4096},
)
```

### Budget guidance

- **1K–2K tokens** — moderate planning, short algebra, code review of a
  single function.
- **4K–8K tokens** — multi-constraint planning, proof sketches, complex
  debugging.
- **16K+** — deep analysis of long artifacts (RFCs, design docs); pair with
  a larger `max_tokens` to fit the answer too.

## Anti-patterns

- **Do not** pipe thinking text into a user-visible UI. Anthropic's policy
  treats thinking blocks as internal reasoning; showing them verbatim is
  out-of-contract and typically low-value for end users.
- **Do not** enable extended thinking on simple classification or retrieval
  tasks. It increases latency and token spend without improving accuracy.
