# Prompts used in recipe 04

## System prompt

```text
You extract structured invoice data from document images. Respond with a
single JSON object matching the schema provided. Do not add commentary,
markdown fences, or keys outside the schema. If a field is not visible in
the image, set it to null.
```

### Why it reads that way

- **"Respond with a single JSON object."** Claude's default chat register
  wants to be helpful in prose. An explicit JSON-only contract stops that.
- **"Do not add ... markdown fences."** In practice Claude still sometimes
  wraps its output in ```` ```json ```` fences. The recipe strips them
  defensively; the system prompt makes stripping rare rather than always.
- **"keys outside the schema"** discourages Claude from adding helpful
  fields like `raw_text` that the Pydantic validator would reject.
- **"If a field is not visible, set it to null."** Explicit null handling is
  cheaper than a retry loop when Claude would otherwise invent plausible
  defaults.

## User turn

The recipe supplies two content blocks in one user message:

1. An ``image`` block (base64-encoded bytes).
2. A ``text`` block carrying the caption and schema documentation.

Splitting blocks rather than interleaving text and image bytes is required
by the Anthropic API shape.
