# Migration from OpenAI to Claude

A pattern-by-pattern migration guide for teams moving from `openai` to `anthropic`. Not a feature-parity table — those go stale. This focuses on the idiom differences that trip teams up.

## The five idiom differences that matter most

1. **Tool use is simpler.** No `function_call` / `tool_calls` indirection; Claude returns tool_use blocks directly in the message content.
2. **Vision is message-level, not URL-level.** You pass image bytes or base64 in a content block, not a URL field.
3. **Prompt caching is first-class.** Mark blocks as cacheable with `cache_control`. Cache reads cost ~10x less than regular input tokens.
4. **Extended thinking is a distinct mode.** You enable `thinking` explicitly; Claude's output then includes `thinking` blocks alongside `text` blocks.
5. **System prompts are top-level.** They're a separate `system` parameter, not a message with role=system.

## Side-by-side: a simple chat call

**OpenAI:**

```python
from openai import OpenAI
client = OpenAI()

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What's 2+2?"},
    ],
    temperature=0.0,
)
text = response.choices[0].message.content
```

**Claude:**

```python
from anthropic import Anthropic
client = Anthropic()

response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    system="You are a helpful assistant.",
    messages=[
        {"role": "user", "content": "What's 2+2?"},
    ],
    temperature=0.0,
)
text = response.content[0].text
```

Differences:
- `system` is a top-level parameter, not a message.
- `max_tokens` is required on Claude.
- Response is `.content[0].text` (a list of content blocks) not `.choices[0].message.content`.

## Tool use

**OpenAI:**

```python
tools = [{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get weather for a city",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string"},
            },
            "required": ["city"],
        },
    },
}]

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Weather in Seoul?"}],
    tools=tools,
    tool_choice="auto",
)

# Tool call lives in tool_calls
tool_call = response.choices[0].message.tool_calls[0]
args = json.loads(tool_call.function.arguments)
```

**Claude:**

```python
tools = [{
    "name": "get_weather",
    "description": "Get weather for a city",
    "input_schema": {
        "type": "object",
        "properties": {
            "city": {"type": "string"},
        },
        "required": ["city"],
    },
}]

response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    tools=tools,
    messages=[{"role": "user", "content": "Weather in Seoul?"}],
)

# Tool use blocks live directly in content
for block in response.content:
    if block.type == "tool_use":
        tool_name = block.name
        tool_input = block.input  # already a dict, no JSON parse
```

Differences:
- Schema field is `input_schema`, not `parameters` nested under `function`.
- Tool calls are content blocks, not a separate `tool_calls` array.
- Arguments are pre-parsed as a dict; no `json.loads` needed.
- Returning tool results also uses content blocks; see recipe 01.

## Multi-turn with tool results

**OpenAI:**

```python
# After getting a tool call, append both the assistant message and the tool result
messages.append({
    "role": "assistant",
    "content": None,
    "tool_calls": response.choices[0].message.tool_calls,
})
messages.append({
    "role": "tool",
    "tool_call_id": tool_call.id,
    "content": json.dumps(tool_result),
})
```

**Claude:**

```python
# Append the assistant's entire content list
messages.append({"role": "assistant", "content": response.content})
# Append a user message with a tool_result content block
messages.append({
    "role": "user",
    "content": [
        {
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": json.dumps(tool_result),
        }
    ],
})
```

Differences:
- Tool results come back as a `user` message, not a `tool` role.
- The `tool_use_id` links to the original tool_use block by id.

## Vision

**OpenAI:**

```python
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{
        "role": "user",
        "content": [
            {"type": "text", "text": "What's in this image?"},
            {"type": "image_url", "image_url": {"url": "https://..."}},
        ],
    }],
)
```

**Claude:**

```python
import base64

with open("invoice.png", "rb") as f:
    image_b64 = base64.standard_b64encode(f.read()).decode("utf-8")

response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=2048,
    messages=[{
        "role": "user",
        "content": [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": image_b64,
                },
            },
            {"type": "text", "text": "What's in this image?"},
        ],
    }],
)
```

Differences:
- Claude wants base64 image bytes, not a URL.
- Media type is explicit (`image/png`, `image/jpeg`, `image/webp`, `image/gif`).
- Order text and image blocks deliberately; Claude reads them top-down.

## Prompt caching

**OpenAI:** Prompt caching is automatic under certain conditions but not user-controllable.

**Claude:**

```python
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    system=[
        {
            "type": "text",
            "text": LARGE_SYSTEM_PROMPT,  # 50K+ tokens
            "cache_control": {"type": "ephemeral"},
        },
    ],
    messages=[{"role": "user", "content": "query"}],
)

# Check cache metrics
print(response.usage.cache_creation_input_tokens)  # First call
print(response.usage.cache_read_input_tokens)       # Subsequent calls
```

Differences:
- Mark specific content blocks as cacheable with `cache_control`.
- Cache lives for ~5 minutes by default (ephemeral).
- Cache reads cost 10% of regular input token price — meaningful savings.
- See recipe 05 for a full walkthrough.

## Extended thinking

OpenAI has `o1`/`o3` reasoning models with thinking baked in. Claude treats thinking as a mode you enable:

```python
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=16000,
    thinking={
        "type": "enabled",
        "budget_tokens": 10000,
    },
    messages=[{"role": "user", "content": "Solve this puzzle: ..."}],
)

# Response contains both thinking blocks and text blocks
for block in response.content:
    if block.type == "thinking":
        print("(model's reasoning):", block.thinking)
    elif block.type == "text":
        print("(final answer):", block.text)
```

Differences:
- You control the thinking budget explicitly.
- Thinking blocks are inspectable (useful for evaluation).
- You pay for thinking tokens — bound the budget appropriately.
- See recipe 07 for a full walkthrough.

## Streaming

Both APIs support streaming, but the event structure differs:

**OpenAI:**

```python
stream = client.chat.completions.create(
    model="gpt-4o",
    messages=[...],
    stream=True,
)
for chunk in stream:
    delta = chunk.choices[0].delta.content
    if delta:
        print(delta, end="")
```

**Claude:**

```python
with client.messages.stream(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    messages=[...],
) as stream:
    for text in stream.text_stream:
        print(text, end="")
    # Access the final message
    final = stream.get_final_message()
```

Differences:
- Claude streams as a context manager with helper iterators.
- You can recover the full final message from the stream object.
- See recipe 09 for interruption handling.

## Batch API

Both APIs now have a batch mode at ~50% pricing:

**OpenAI:** `client.batches.create(...)` with a JSONL file.

**Claude:** `client.beta.messages.batches.create(...)` with in-memory request list or JSONL. See recipe 06.

Differences:
- Claude's batch API accepts up to 10K requests per batch.
- Processing time is typically faster for small batches (minutes vs hours).
- Same pricing discount.

## Error handling

**OpenAI:** `openai.APIError`, `openai.RateLimitError`, etc.

**Claude:** `anthropic.APIError`, `anthropic.RateLimitError`, `anthropic.APIStatusError`, etc.

Idiomatic retry:

```python
from anthropic import RateLimitError, APIStatusError
import time

def call_with_retry(client, **kwargs):
    for attempt in range(5):
        try:
            return client.messages.create(**kwargs)
        except RateLimitError:
            time.sleep(2 ** attempt)
        except APIStatusError as e:
            if e.status_code >= 500:
                time.sleep(2 ** attempt)
            else:
                raise
    raise RuntimeError("retries exhausted")
```

See `common/client.py` for the retry wrapper this cookbook uses.

## Model naming

| OpenAI | Claude equivalent (April 2026) |
|--------|-------------------------------|
| gpt-4o | claude-sonnet-4-20250514 |
| gpt-4o-mini | claude-haiku-4-20250807 |
| o1 / o3 | claude-sonnet-4 with extended thinking enabled |
| gpt-4-turbo (legacy) | claude-sonnet-3-5-20241022 (legacy) |

Always pin a model version in production; "latest" aliases shift.

## Cost shape

Claude on Sonnet 4 is roughly comparable to GPT-4o for most workloads. The big wins:

- **Prompt caching** drops repeat-prompt cost by 90%. Use it aggressively.
- **Batch API** drops offline workload cost by 50%.
- **Haiku 4** is faster and cheaper than Haiku 3 while matching Sonnet 3.5 quality on many tasks.

## What to do in your migration

1. **Start with the shared client wrapper** (`common/client.py` in this cookbook). Port your retry/logging to match.
2. **Pick one feature to migrate first**: usually the largest system-prompt consumer, to validate prompt caching savings.
3. **Keep both clients running side-by-side** for the highest-traffic flows. Compare outputs on 100 requests. Only cut over after the comparison is clean.
4. **Re-tune your prompts**. Claude responds differently to identical prompts. Expect 2-5 prompt revisions per migrated flow.
5. **Re-run your eval suite**. If you don't have one, see recipe 10. Migrating without evals is how regressions ship.

## Don't do this

- Don't wholesale copy OpenAI prompts and expect identical behavior. Claude is more literal about instructions and more verbose by default.
- Don't skip `max_tokens`. It's required, and setting it too low truncates responses silently.
- Don't use high temperature (>0.5) for tool-use flows. Claude's tool-use determinism benefits from temperature=0 or 0.1.
- Don't reuse OpenAI's `tool_choice="required"` pattern thoughtlessly. Claude has the equivalent (`tool_choice={"type": "any"}`) but tool-use failure modes differ.
