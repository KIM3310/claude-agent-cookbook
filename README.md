# claude-agent-cookbook

> Production-grade recipes for building agents on Claude. Each pattern is a runnable example with tests, prompts, and notes on when to use it — designed for teams shipping Claude-powered products.

[![CI](https://github.com/KIM3310/claude-agent-cookbook/actions/workflows/ci.yml/badge.svg)](https://github.com/KIM3310/claude-agent-cookbook/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![Anthropic SDK](https://img.shields.io/badge/anthropic-%3E%3D0.39-663399.svg)](https://github.com/anthropics/anthropic-sdk-python)

---

## Why this exists

Anthropic's own Claude cookbook is excellent for learning the SDK surface. This repository is complementary: it focuses on **production patterns** — the shape of code that runs in a real product — and on **evaluation**, so teams can measure whether their Claude integration is actually working before shipping.

Every recipe is:

- A runnable Python file (`recipe.py`) that works against the real Claude API.
- A mocked test suite (`test_recipe.py`) that runs in CI without an API key.
- A commented `prompt.md` explaining the system + user prompt design.
- An `expected_output.json` fixture so you know what "working" looks like.
- A scoped README explaining when to use the pattern and when not to.

This pack is built by Doeon Kim ([@KIM3310](https://github.com/KIM3310)) and complements his [stage-pilot](https://github.com/KIM3310/stage-pilot) tool-calling reliability runtime. Where stage-pilot is the runtime infrastructure, this cookbook is the reference implementation of agent patterns that run on top.

## The Recipes

| # | Recipe | Problem it solves | Claude features used | Complexity |
|---|--------|-------------------|----------------------|-----------|
| 01 | [tool-use](recipes/01-tool-use/) | Single-turn agent calling a typed tool | `tools` parameter, tool_use blocks | Low |
| 02 | [multi-turn-tool-use](recipes/02-multi-turn-tool-use/) | Agent that chains 3 tool calls to complete a workflow | Multi-turn conversation with tool results | Medium |
| 03 | [rag](recipes/03-rag/) | Answer questions from a corpus with citations | Retrieval + structured response + citations | Medium |
| 04 | [vision](recipes/04-vision/) | Extract structured JSON from images (invoice processing) | Vision input + structured output | Medium |
| 05 | [prompt-caching](recipes/05-prompt-caching/) | Cache large system prompts to reduce cost and latency | `cache_control` blocks | Low |
| 06 | [batch-api](recipes/06-batch-api/) | Run 100+ prompts asynchronously at half price | Message Batches API | Low |
| 07 | [extended-thinking](recipes/07-extended-thinking/) | Hard reasoning problems benefit from explicit thinking | Extended thinking (`thinking` parameter) | Medium |
| 08 | [multi-agent](recipes/08-multi-agent/) | Coordinator Claude routes subtasks to specialist Claudes | Multi-message orchestration, tool use between agents | High |
| 09 | [streaming-with-interruption](recipes/09-streaming-with-interruption/) | Stream responses, let users cancel mid-generation | Streaming + cancellation + partial-result handling | High |
| 10 | [eval-framework](recipes/10-eval-framework/) | Regression-test your Claude prompts | Rubric-based eval, gold-set comparison | Medium |

## Quick Start

```bash
# 1. Install
git clone https://github.com/KIM3310/claude-agent-cookbook.git
cd claude-agent-cookbook
make install

# 2. Configure your API key
cp .env.example .env
# edit .env and set ANTHROPIC_API_KEY

# 3. Run a recipe
make recipe NAME=01-tool-use
# or directly:
python -m recipes.01-tool-use.recipe --prompt "what's the weather in Seoul?"

# 4. Run the test suite (no API key needed — all tests mock the client)
make test
```

## The common/ layer

Every recipe imports from `common/`:

- **`common/client.py`** — Anthropic client wrapper with retry, token counting, cost estimation, and structured logging hooks. Use this, not `anthropic.Anthropic()` directly, in any code that's going to run in production.
- **`common/eval.py`** — the evaluation framework used by recipe 10. Re-usable for regression-testing your own prompts.
- **`common/tools.py`** — Pydantic v2 models for the tool definitions shared across recipes. Type-safe, validates Claude's tool_use arguments at the boundary.
- **`common/logging.py`** — structured logging setup. Emits JSON; drops into any log aggregator (Datadog, Loki, CloudWatch).
- **`common/types.py`** — `TypedDict`s and Pydantic models for the shared data types.

The common layer has 80%+ test coverage. Recipes depend on it; it doesn't depend on any recipe.

## Running Recipes

### With a real API key

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python -m recipes.03-rag.recipe --query "How do I enable prompt caching?"
```

Expected cost: typically under $0.05 per recipe run on Claude Sonnet 4 at current pricing. See each recipe's README for specifics.

### Without an API key (tests only)

```bash
pytest recipes/ -v
pytest common/ -v
```

All tests mock the Anthropic client. CI runs them on every push.

## Evaluation Framework

Recipe 10 (`recipes/10-eval-framework/`) wraps `common/eval.py` with:

- A gold set (`example_gold_set.jsonl`) of prompt/expected-answer pairs.
- Rubric-based scoring (faithfulness, groundedness, relevance).
- Regression detection: compare today's run against a baseline and fail CI on regression.
- Sample report output in `reports/sample_report.md`.

Use the eval framework before changing a production prompt. It's the cheapest insurance you can buy against silent quality regressions.

## Migration from OpenAI

If your codebase currently uses `openai`, see [docs/migration-from-openai.md](docs/migration-from-openai.md) for a pattern-by-pattern migration guide. The big differences:

- Tool use is simpler in Claude (no `function_call`/`tool_calls` indirection).
- Vision is message-level, not image-URL-level.
- Prompt caching is first-class and reduces cost materially.
- Extended thinking is a distinct mode, not a prompt engineering trick.

## When to Use What

See [docs/when-to-use-what.md](docs/when-to-use-what.md) for a decision tree mapping business problems to recipes. Summary:

- **One tool, one turn** → recipe 01.
- **Chain of tools** → recipe 02.
- **"Answer from our docs"** → recipe 03.
- **"Read this PDF/invoice/receipt"** → recipe 04.
- **Big static system prompt** → recipe 05.
- **100+ prompts to run overnight** → recipe 06.
- **"Think through this carefully"** → recipe 07.
- **Coordinator + specialists** → recipe 08.
- **User-facing streaming UI** → recipe 09.
- **Regression-test your prompts** → recipe 10.

## Production Considerations

See [docs/production-considerations.md](docs/production-considerations.md). Highlights:

- Rate limits and exponential backoff.
- Cost monitoring (cap spend before it's a problem).
- Error classification (transient vs permanent).
- Prompt version pinning.
- Model version migration strategy.

## Project Structure

```
claude-agent-cookbook/
├── README.md                    # This file
├── LICENSE                      # MIT
├── Makefile                     # install / test / recipe NAME=...
├── pyproject.toml               # Python 3.11+, anthropic>=0.39, pytest, mypy
├── requirements.txt
├── .env.example                 # Template for API key
├── .gitignore
├── .github/workflows/ci.yml     # mypy + pytest
├── common/                      # Shared client, eval, tools, logging, types
│   └── test_*.py                # Unit tests for the common layer
├── recipes/
│   ├── 01-tool-use/
│   │   ├── README.md
│   │   ├── recipe.py            # Runnable
│   │   ├── test_recipe.py       # Mocked, runs in CI
│   │   ├── prompt.md            # Annotated prompt design
│   │   └── expected_output.json
│   ├── 02-multi-turn-tool-use/
│   ├── 03-rag/
│   │   └── corpus/              # Text documents to retrieve over
│   ├── 04-vision/
│   │   └── samples/             # Placeholder images
│   ├── 05-prompt-caching/
│   ├── 06-batch-api/
│   │   └── batch_input.jsonl
│   ├── 07-extended-thinking/
│   ├── 08-multi-agent/
│   ├── 09-streaming-with-interruption/
│   └── 10-eval-framework/
│       ├── framework.py
│       ├── rubrics.py
│       ├── example_gold_set.jsonl
│       └── reports/sample_report.md
├── docs/
│   ├── when-to-use-what.md
│   ├── production-considerations.md
│   ├── migration-from-openai.md
│   └── adr/
│       ├── 001-client-wrapper-design.md
│       └── 002-eval-rubric-strategy.md
└── scripts/
    └── run_recipe.sh
```

## Related Projects

| Project | Relationship |
|---------|-------------|
| [stage-pilot](https://github.com/KIM3310/stage-pilot) | Tool-calling reliability runtime. The recipes in this cookbook run on top of (or alongside) stage-pilot's retry/validation layer. |
| [agent-orchestration-benchmark](https://github.com/KIM3310/agent-orchestration-benchmark) | Benchmark harness comparing agent frameworks — uses many of the same patterns as recipes 01-02 and 08. |
| [AegisOps](https://github.com/KIM3310/AegisOps) | Multimodal incident analysis built on Claude; operator-handoff pattern informs recipe 08. |
| [enterprise-llm-adoption-kit](https://github.com/KIM3310/enterprise-llm-adoption-kit) | Enterprise LLM governance (RAG, RBAC, audit). Recipe 03's retrieval pattern scales into this. |
| [Nexus-Hive](https://github.com/KIM3310/Nexus-Hive) | Multi-agent NL-to-SQL copilot. Recipe 08's coordinator pattern is the reference. |

## Contributing

Contributions welcome. Open an issue describing the production pattern you've seen that's missing, and we can discuss whether to add it as recipe #11+.

When contributing a new recipe, follow the existing structure:
1. Create a `recipes/NN-name/` directory.
2. Write `README.md` first (forces you to articulate the problem).
3. Implement `recipe.py` with proper error handling.
4. Add `test_recipe.py` with mocked Claude responses.
5. Add `prompt.md` explaining the prompt design.
6. Commit `expected_output.json` as a fixture.
7. Add your recipe to this README's table.

## License

MIT. See [LICENSE](LICENSE).

## Citation

If you use these recipes in academic work or a technical talk, citation is appreciated but not required:

```bibtex
@misc{kim2026claudeagentcookbook,
  title={Claude Agent Cookbook: Production Patterns for Anthropic's Claude},
  author={Kim, Doeon},
  year={2026},
  howpublished={\url{https://github.com/KIM3310/claude-agent-cookbook}},
}
```

## Cloud + AI Architecture

This repository includes a neutral cloud and AI engineering blueprint that maps the current proof surface to runtime boundaries, data contracts, model-risk controls, deployment posture, and validation hooks.

- [Cloud + AI architecture blueprint](docs/cloud-ai-architecture.md)
- [Machine-readable architecture manifest](architecture/blueprint.json)
- Validation command: `python3 scripts/validate_architecture_blueprint.py`
