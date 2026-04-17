# Extended thinking

Extended thinking enables Claude to produce hidden reasoning before its final
answer. You opt in per request by setting the `thinking` parameter with
`{"type": "enabled", "budget_tokens": N}`. When enabled, the response
contains one or more `thinking` content blocks whose text should not be shown
verbatim to end users. The visible answer appears in the usual `text`
blocks.

Extended thinking is best suited to multi-step reasoning problems: algebra,
planning, code review, evaluation rubrics. It increases latency and output
token consumption; budget between 1K and 16K thinking tokens depending on
task depth. Avoid extended thinking for simple retrieval or conversational
tasks where it adds cost without improving quality.
