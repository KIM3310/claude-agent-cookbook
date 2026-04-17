# Streaming

Use the streaming API to receive tokens as they are generated. Set
`stream=True` (or use the `messages.stream` helper) and iterate over
server-sent events of type `content_block_delta`, `message_delta`, and
`message_stop`. Streaming reduces perceived latency and enables
cancellation: closing the HTTP connection halts generation and stops token
billing from that point on.

For user-facing chat UIs, always stream. Preserve partial text on abort so a
user-triggered cancellation does not discard the model's progress. Recipe 09
demonstrates the pattern.
