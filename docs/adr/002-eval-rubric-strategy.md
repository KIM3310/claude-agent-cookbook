# ADR 002: Eval Rubric Strategy

- **Status**: Accepted
- **Date**: 2026-04-17

## Context

Recipe 10 implements an evaluation framework. The framework's central abstraction is the **rubric**: how do we score "this Claude response is good"?

Options considered:

1. **Exact match**: compare response text to expected text.
2. **Keyword presence**: check that required keywords appear.
3. **LLM-as-judge**: ask Claude to score the response.
4. **Structured rubric**: multiple named criteria, each scored independently.
5. **Embedding similarity**: cosine similarity between response and reference.

## Decision

Adopt **Option 4 — structured rubric**, with Option 2 (keyword presence) and Option 3 (LLM-as-judge) as specific rubric criterion types.

Every rubric is a list of named criteria. Each criterion has:
- `name`: human-readable identifier.
- `weight`: contribution to final score.
- `evaluator`: function that takes a response and returns `(score: float in [0,1], explanation: str)`.
- `gate`: if `True`, a failure on this criterion fails the overall eval regardless of other criteria (useful for "must have citation" type requirements).

Criterion types available out of the box:
- `KeywordPresenceCriterion`: fails if required keywords missing.
- `RegexCriterion`: fails if regex doesn't match.
- `LLMJudgeCriterion`: wraps an LLM-as-judge call with a specific prompt.
- `StructuredOutputCriterion`: validates JSON structure against a schema.
- `FaithfulnessCriterion`: LLM-as-judge specialized for RAG faithfulness.
- `GroundednessCriterion`: LLM-as-judge specialized for groundedness in retrieved context.
- `LatencyCriterion`: fails if response took too long.
- `CostCriterion`: fails if response cost exceeded budget.

Users compose criteria into rubrics per use case.

## Consequences

### Positive

- **Explicit failure modes**: each criterion tells you *why* a response failed. "Missing keyword: citation" is more actionable than a scalar score.
- **Regression detection**: per-criterion scores track over time. You see which dimension is drifting.
- **Mix-and-match**: deterministic criteria (keyword, regex) + LLM-based criteria (LLM-judge) in the same rubric. Cheap criteria gate expensive ones.
- **Extensible**: new criterion types are small classes. Users add domain-specific ones without touching the framework core.
- **Auditable**: rubric definitions are declarative Python; they check into git and diff meaningfully.

### Negative

- **Up-front effort**: writing a rubric for a new prompt requires 10-20 minutes of thinking about what "good" means. Vs "compare to gold answer" which is zero thinking.
- **LLM-judge bias**: LLMJudgeCriterion uses Claude to score Claude; there's a bias toward patterns Claude produces. We mitigate by having the judge use a different temperature or a different model version.
- **Rubric maintenance**: as the application evolves, rubrics need revision. We accept this cost because the alternative — not evaluating — is worse.

### Mitigations

- Provide pre-built rubric templates for common tasks (faithfulness, groundedness, structured output conformance) so teams don't start from scratch.
- Document the LLM-judge bias in `docs/production-considerations.md` and recommend cross-validation with human spot-checks.
- Encourage versioning rubrics alongside prompts (e.g., `prompt_v3.md` → `rubric_v3.py`).

## Alternatives considered

### Option 1 — exact match

Rejected. Claude responses are not deterministic in phrasing even at temperature=0. Exact match produces false negatives on semantically correct answers.

### Option 2 — keyword presence (alone)

Partially accepted as a criterion type. Insufficient as a whole strategy: a response can have all required keywords yet be factually wrong, off-topic, or internally inconsistent.

### Option 3 — LLM-as-judge (alone)

Partially accepted as a criterion type. Insufficient as a whole strategy: LLM-judge is expensive, slow, and has its own reliability concerns. Deterministic criteria should gate LLM-judge calls.

### Option 5 — embedding similarity

Rejected for this cookbook. Embedding similarity is sensitive to surface-level phrasing and doesn't capture the criteria that actually matter in production (did it cite? did it call the right tool? did it follow the output schema?). It's useful in specific cases (deduplication, clustering) but not as the primary eval substrate.

### Option 6 — pairwise comparison (A/B with human raters)

Rejected as baseline; out of scope for an engineering-side framework. Teams that need this can build pairwise comparison on top of our rubric framework by implementing a `PairwiseCriterion`.

## Implementation details

Core types in `common/eval.py`:

```python
class Criterion(ABC):
    name: str
    weight: float = 1.0
    gate: bool = False

    @abstractmethod
    def evaluate(self, response: Response, context: EvalContext) -> CriterionResult:
        ...

@dataclass
class CriterionResult:
    criterion_name: str
    score: float  # in [0, 1]
    passed: bool
    explanation: str
    metadata: dict[str, Any] = field(default_factory=dict)

class Rubric:
    criteria: list[Criterion]

    def evaluate(self, response: Response, context: EvalContext) -> RubricResult:
        ...

@dataclass
class RubricResult:
    criterion_results: list[CriterionResult]
    aggregate_score: float
    passed: bool
    gate_failures: list[str]
```

Aggregation rule:
- If any `gate` criterion fails, the rubric fails, regardless of other scores.
- Otherwise, `aggregate_score = sum(c.score * c.weight) / sum(c.weight)`.
- Rubric passes if `aggregate_score >= pass_threshold` (default 0.7).

## How to add a new criterion type

1. Subclass `Criterion`.
2. Implement `evaluate(response, context) -> CriterionResult`.
3. Add tests to `common/test_eval.py`.
4. Document the new criterion in `recipes/10-eval-framework/README.md`.

## Reference reports

`recipes/10-eval-framework/reports/sample_report.md` shows a typical report output:

- Summary line (pass/fail, aggregate score).
- Per-criterion breakdown.
- Regression delta vs baseline (if baseline provided).
- Per-test failure explanations.

## References

- `common/eval.py` — implementation.
- `recipes/10-eval-framework/rubrics.py` — example rubric definitions (Faithfulness, Groundedness).
- `recipes/10-eval-framework/example_gold_set.jsonl` — sample dataset.
- OpenAI's evals library (for comparison): https://github.com/openai/evals
- PromptFoo: https://promptfoo.dev (similar philosophy, different implementation)
