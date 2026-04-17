# Prompt caching

Prompt caching lets you mark stable prefixes of a system prompt so that
subsequent requests reuse the server-side computation. Savings come from a
reduced price per cached input token and from lower end-to-end latency.

Cache breakpoints are set by adding `cache_control: {"type": "ephemeral"}` to
a system-prompt block or a tools definition. Claude charges a one-time cache
write fee at a 25% premium, then reads at roughly 10% of the normal input
token price. Typical applications see large savings when a long static
preamble is shared across many short user questions.
