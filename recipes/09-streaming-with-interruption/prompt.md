# Prompts used in recipe 09

## System prompt

This recipe takes any system prompt; it does not attempt to tune the persona.
The goal is to exercise the streaming surface and the cancellation semantics,
so the user supplies the prompt directly:

```text
Explain prompt caching in 200 words.
```

## Streaming event shapes consumed

The driver listens for the following SDK events:

- `content_block_delta` with `delta.type = "text_delta"` — carries the
  incremental text chunk.
- `message_delta` — carries `stop_reason` and the running `usage`.
- `message_stop` — terminal event with final `usage`.

All other event types (`message_start`, `content_block_start`,
`content_block_stop`, `ping`) are ignored.

## Cancellation contract

- The UI thread calls `session.cancel()` at any time.
- The driver checks `session.is_cancelled()` before processing each event.
- When cancellation is observed, the driver exits the event loop; the
  SDK's context manager closes the HTTP connection on exit.
- `session.text` returns whatever was accumulated before cancellation.
- `session.stop_reason` is set to `"cancelled"`.

This contract means "click Stop" does not discard partial output, which is
what users expect.
