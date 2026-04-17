# Prompts used in recipe 01

## System prompt

```text
You are a concise weather assistant. When a user asks about the weather in a
city, call the `get_weather` tool exactly once. After receiving the tool
result, respond in a single sentence with the temperature and a brief
description. Do not invent data.
```

### Why it looks the way it does

- "exactly once" curbs tool-overuse — a well-known failure mode when Claude
  is given tools it does not strictly need.
- "Do not invent data" is a specific instruction against hallucinated weather
  numbers when the tool fails. Paired with the `is_error=true` tool result,
  Claude will surface the failure rather than paper over it.
- The response contract ("a single sentence with the temperature and a brief
  description") is short enough that a rubric can verify compliance without
  an LLM judge.

## Example user prompts

```text
What's the weather in Seoul right now?
Is it raining in London?
How warm is Tokyo today? Use fahrenheit.
```

## Tool schema exposed to Claude

```json
{
  "name": "get_weather",
  "description": "Look up current weather for a city by name.",
  "input_schema": {
    "type": "object",
    "properties": {
      "city": {"type": "string", "description": "City name, for example 'Seoul' or 'San Francisco'."},
      "unit": {"type": "string", "description": "Temperature unit. One of: 'celsius', 'fahrenheit'.", "default": "celsius"}
    },
    "required": ["city"]
  }
}
```
