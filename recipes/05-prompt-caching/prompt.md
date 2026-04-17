# Prompts used in recipe 05

## Structure

System prompt is a *list of typed blocks* rather than a single string:

```python
[
    {"type": "text", "text": "You are 'Atlas', ..."},
    {"type": "text", "text": "<~3K token handbook>", "cache_control": {"type": "ephemeral"}},
]
```

The short preamble comes first and is *not* marked cacheable. The long
handbook follows and carries the `cache_control` breakpoint. Anthropic caches
every block up to and including the first block with `cache_control`, so the
handbook (and the preamble above it) becomes the cached prefix.

## Why put the small block first

It is counterintuitive: you might put the long, rarely-changing handbook at
the start. But cache breakpoints cache *the prefix up to* the breakpoint, so
placing the breakpoint on the handbook cached everything up to and including
the handbook — this is exactly what we want, because the preamble is also
stable across calls.

If you add, say, a per-tenant customization *before* the cached block, you
would bust the cache for every tenant switch. Put stable text first.

## User prompt shape

User prompts are short and vary per request; they are never marked cacheable.

```text
Summarize Section 01 in one sentence.
```

## Minimum cache size

Claude enforces a minimum prefix length for caching (check Anthropic docs for
the current number). This recipe generates a ~3K-token handbook body so the
breakpoint is always large enough to be honored. If you cache below the
minimum, the API returns `cache_creation_input_tokens=0` and charges full
input prices.
