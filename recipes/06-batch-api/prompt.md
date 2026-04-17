# Prompts used in recipe 06

## System prompt (per request)

```text
You label sentiment as one of: positive, neutral, negative. Respond with one word.
```

### Rationale

- **One-word responses** keep the output tokens low across 100 requests.
  With Sonnet pricing at $15/mtok output, even a verbose model can spike
  costs on bulk jobs.
- **Closed label set** makes downstream rubric scoring trivial: a
  case-insensitive `in {"positive", "neutral", "negative"}` check is enough.
- **Absence of examples.** For simple classification Claude is usually good
  without few-shot exemplars. Add examples only if the eval baseline shows
  bias toward "neutral" on your domain.

## User prompt shape

Each row varies `custom_id` and the user text:

```text
Classify the sentiment of this sentence: '<text>'.
```

## batch_input.jsonl format

Each line is a single JSON object:

```json
{
  "custom_id": "eval-0000",
  "params": {
    "model": "claude-sonnet-4-20250514",
    "max_tokens": 256,
    "system": "You label sentiment ...",
    "messages": [{"role": "user", "content": "Classify the sentiment..."}]
  }
}
```

The recipe generates this file with 100 entries so running the end-to-end
CLI is a one-command smoke test.
