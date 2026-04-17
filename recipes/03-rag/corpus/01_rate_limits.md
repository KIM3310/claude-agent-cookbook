# Rate limits

Anthropic's API applies two independent rate limits: requests per minute (RPM)
and tokens per minute (TPM). Both are enforced per-organization and reset on
rolling windows. When a request exceeds either limit, the API returns HTTP 429
with an `anthropic-ratelimit-*` header indicating how many seconds to wait
before retrying. Production clients should honor these headers rather than
retrying immediately.

Higher usage tiers are available on request. The SDK includes built-in
exponential backoff that respects the `retry-after` header.
