# When to use what: a decision guide

The 10 recipes in this cookbook map onto the recurring shapes of real
Claude-powered products. This document turns that mapping into a decision
tree so teams can pick the right pattern fast.

## Quick decision tree

```
Is the task well-defined as one turn and one tool?
├── Yes → Recipe 01 (single-turn tool use)
└── No
    │
    ├── Does the task need a chain of tool calls with ordering?
    │   └── Yes → Recipe 02 (multi-turn tool use)
    │
    ├── Is the answer grounded in a body of text?
    │   └── Yes → Recipe 03 (RAG with citations)
    │
    ├── Is the input an image or document?
    │   └── Yes → Recipe 04 (vision structured extraction)
    │
    ├── Is a big, stable prefix shared across many requests?
    │   └── Yes → Recipe 05 (prompt caching)
    │
    ├── Are you running N ≥ 100 prompts offline?
    │   └── Yes → Recipe 06 (Batch API)
    │
    ├── Is the problem constraint-heavy (planning / algebra)?
    │   └── Yes → Recipe 07 (extended thinking)
    │
    ├── Does the task decompose into distinct personas?
    │   └── Yes → Recipe 08 (coordinator + specialists)
    │
    ├── Is the output user-facing and interruptible?
    │   └── Yes → Recipe 09 (streaming + cancellation)
    │
    └── (Always, alongside the above) → Recipe 10 (eval framework)
```

## Side-by-side matrix

| Dimension                 | 01  | 02  | 03  | 04  | 05  | 06  | 07  | 08  | 09  | 10  |
|---------------------------|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|
| Tool use                  | Yes | Yes |  -  |  -  |  -  |  -  |  -  | Yes |  -  |  -  |
| Multi-turn loop           |  -  | Yes |  -  |  -  |  -  |  -  |  -  | Yes |  -  |  -  |
| Retrieval                 |  -  |  -  | Yes |  -  |  -  |  -  |  -  |  -  |  -  |  -  |
| Vision                    |  -  |  -  |  -  | Yes |  -  |  -  |  -  |  -  |  -  |  -  |
| Prompt caching            |  -  |  -  |  -  |  -  | Yes |  -  |  -  |  -  |  -  |  -  |
| Batch API                 |  -  |  -  |  -  |  -  |  -  | Yes |  -  |  -  |  -  |  -  |
| Extended thinking         |  -  |  -  |  -  |  -  |  -  |  -  | Yes |  -  |  -  |  -  |
| Multi-agent               |  -  |  -  |  -  |  -  |  -  |  -  |  -  | Yes |  -  |  -  |
| Streaming                 |  -  |  -  |  -  |  -  |  -  |  -  |  -  |  -  | Yes |  -  |
| Evaluation                |  -  |  -  |  -  |  -  |  -  |  -  |  -  |  -  |  -  | Yes |
| Recommended latency       | Low | Med | Low | Med | Low | Async | High | High | Low | CI |

## Business problem → recipe mapping

- "Answer a policy question with a citation" → Recipe 03.
- "Let users ask about last month's weather" → Recipe 01.
- "Book a flight end-to-end" → Recipe 02.
- "Extract vendor totals from invoices dropped into a folder" → Recipe 04.
- "My assistant has a 15-page operational runbook in its system prompt" →
  Recipe 05.
- "Label 20K reviews this weekend" → Recipe 06 + Recipe 10.
- "Plan a customer onboarding pathway with 9 constraints" → Recipe 07.
- "Draft a launch deliverable with positioning, copy, and engineering plan" →
  Recipe 08.
- "Our chat UI should stop generating when the user clicks Stop" → Recipe 09.
- "Check our agent didn't regress after last week's prompt change" → Recipe 10.

## Anti-patterns

- **Using Recipe 07 for simple retrieval.** Extended thinking makes the
  answer slower and more expensive without improving quality.
- **Using Recipe 08 where Recipe 02 would do.** A single multi-turn loop
  with three tools is simpler and cheaper than three personas whenever the
  personas are not meaningfully different.
- **Skipping Recipe 10.** Every other recipe benefits from a gold-set eval.
  Putting it off is the most common path to silent regressions.
- **Recipe 05 without measurement.** Prompt caching only helps when the
  prefix is large and reused. Measure `cache_read_input_tokens` before
  assuming it's working.
