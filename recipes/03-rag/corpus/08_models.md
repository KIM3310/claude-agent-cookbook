# Claude model family

The Claude family spans three tiers. Haiku is the smallest and cheapest,
optimized for latency-sensitive classification and tool dispatch. Sonnet is
the workhorse for most applied AI workloads, balancing capability and price.
Opus is the most capable and the most expensive, reserved for deep reasoning
or long-context synthesis tasks.

Model IDs follow the pattern `claude-{tier}-{version}-{date}`. The default
recommended for new development is the current Sonnet release. Always pin a
specific model ID in production and update deliberately; do not rely on
aliases in production code paths that carry evaluation baselines.
