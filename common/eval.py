"""Evaluation framework for Claude-powered recipes.

The framework is deliberately small — it optimizes for being *understood at a
glance* and being easy to wire into CI. It supports three layers of evaluation:

1. **Deterministic checks** via :class:`Rubric` sub-classes (keyword presence,
   exact match, JSON-schema conformance, numeric tolerance).
2. **LLM-as-judge** scoring via :class:`JudgeRubric`, which calls a Claude
   model with a scoring prompt and parses a numeric score.
3. **Regression detection** by comparing a fresh run against a historical
   baseline report.

Typical usage::

    suite = EvalSuite(
        name="rag-faithfulness",
        cases=load_jsonl("gold.jsonl"),
        rubrics=[FaithfulnessRubric(), KeywordPresenceRubric(["citation"])],
    )
    report = run_suite(suite, run_one=my_recipe_callable)
    report.write("reports/latest.md")
    report.assert_no_regression_against("reports/baseline.json")
"""

from __future__ import annotations

import json
import re
import statistics
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from common.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Case + rubric primitives
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class EvalCase:
    """A single gold-set entry.

    - ``prompt`` / ``input`` — what gets sent into the system under test.
    - ``expected`` — ground-truth answer or structured reference.
    - ``metadata`` — freeform tags for slicing reports (``locale``, ``topic``).
    """

    case_id: str
    prompt: str
    expected: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> EvalCase:
        return cls(
            case_id=str(payload["case_id"]),
            prompt=str(payload["prompt"]),
            expected=payload.get("expected"),
            metadata=dict(payload.get("metadata", {})),
        )


Verdict = Literal["pass", "fail", "skip"]


@dataclass(slots=True)
class RubricScore:
    rubric: str
    score: float  # 0.0 .. 1.0
    verdict: Verdict
    detail: str = ""


class Rubric:
    """Base class for all rubrics.

    Sub-classes override :meth:`evaluate` to return a :class:`RubricScore`.
    Rubrics should be *cheap, deterministic, and side-effect-free* whenever
    possible so they can run on every CI build without incurring LLM cost.
    """

    name: str = "rubric"
    weight: float = 1.0

    def evaluate(self, *, case: EvalCase, actual: str) -> RubricScore:  # pragma: no cover - abstract
        raise NotImplementedError


class KeywordPresenceRubric(Rubric):
    """Score by fraction of expected keywords present in the response."""

    name = "keyword_presence"

    def __init__(self, keywords: Iterable[str], *, case_insensitive: bool = True) -> None:
        self.keywords = list(keywords)
        self.case_insensitive = case_insensitive

    def evaluate(self, *, case: EvalCase, actual: str) -> RubricScore:
        haystack = actual.lower() if self.case_insensitive else actual
        hits = [k for k in self.keywords if (k.lower() if self.case_insensitive else k) in haystack]
        if not self.keywords:
            return RubricScore(self.name, 1.0, "pass", "no keywords configured")
        score = len(hits) / len(self.keywords)
        verdict: Verdict = "pass" if score >= 0.5 else "fail"
        detail = f"matched {len(hits)}/{len(self.keywords)} keywords: {hits}"
        return RubricScore(self.name, score, verdict, detail)


class ExactMatchRubric(Rubric):
    """Pass iff ``actual.strip() == case.expected.strip()``."""

    name = "exact_match"

    def evaluate(self, *, case: EvalCase, actual: str) -> RubricScore:
        expected = str(case.expected or "").strip()
        got = actual.strip()
        ok = expected == got
        return RubricScore(
            self.name,
            1.0 if ok else 0.0,
            "pass" if ok else "fail",
            "" if ok else f"expected={expected!r} actual={got!r}",
        )


class JSONSchemaRubric(Rubric):
    """Pass iff ``actual`` parses as JSON and contains all required keys."""

    name = "json_schema"

    def __init__(self, required_keys: Iterable[str]) -> None:
        self.required_keys = list(required_keys)

    def evaluate(self, *, case: EvalCase, actual: str) -> RubricScore:
        try:
            parsed = json.loads(actual)
        except json.JSONDecodeError as exc:
            return RubricScore(self.name, 0.0, "fail", f"invalid JSON: {exc}")
        if not isinstance(parsed, dict):
            return RubricScore(self.name, 0.0, "fail", "JSON is not an object")
        missing = [k for k in self.required_keys if k not in parsed]
        if missing:
            return RubricScore(self.name, 0.0, "fail", f"missing keys: {missing}")
        return RubricScore(self.name, 1.0, "pass", f"all {len(self.required_keys)} keys present")


class NumericToleranceRubric(Rubric):
    """Score numeric answers within an absolute tolerance window."""

    name = "numeric_tolerance"
    _NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")

    def __init__(self, tolerance: float = 0.01) -> None:
        self.tolerance = tolerance

    def evaluate(self, *, case: EvalCase, actual: str) -> RubricScore:
        expected = case.expected
        if not isinstance(expected, (int, float)):
            return RubricScore(self.name, 0.0, "skip", "expected is not numeric")
        match = self._NUMBER_RE.search(actual)
        if not match:
            return RubricScore(self.name, 0.0, "fail", "no number found in actual")
        got = float(match.group(0))
        delta = abs(got - float(expected))
        ok = delta <= self.tolerance
        return RubricScore(
            self.name,
            1.0 if ok else max(0.0, 1.0 - delta),
            "pass" if ok else "fail",
            f"expected={expected} got={got} delta={delta:.4f}",
        )


class JudgeRubric(Rubric):
    """LLM-as-judge rubric.

    Calls a Claude client with a scoring prompt. Returns a score in [0, 1]
    parsed from the judge's output. The judge prompt asks explicitly for a
    single numeric score on the first line to make parsing robust.
    """

    name = "llm_judge"
    _SCORE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*$", re.MULTILINE)

    DEFAULT_TEMPLATE = (
        "You are grading an AI assistant's answer against an expected response.\n"
        "Respond with a single number on the first line, 0 to 10, where 10 is a perfect match.\n"
        "Then, on following lines, explain your grade.\n\n"
        "QUESTION:\n{prompt}\n\n"
        "EXPECTED:\n{expected}\n\n"
        "ACTUAL:\n{actual}\n"
    )

    def __init__(
        self,
        judge_client: Any,
        *,
        model: str | None = None,
        template: str = DEFAULT_TEMPLATE,
        passing_score: float = 0.7,
    ) -> None:
        self.judge_client = judge_client
        self.model = model
        self.template = template
        self.passing_score = passing_score

    def evaluate(self, *, case: EvalCase, actual: str) -> RubricScore:
        prompt = self.template.format(
            prompt=case.prompt,
            expected=case.expected if case.expected is not None else "(none)",
            actual=actual,
        )
        result = self.judge_client.create_message(
            messages=[{"role": "user", "content": prompt}],
            model=self.model,
            max_tokens=256,
        )
        match = self._SCORE_RE.search(result.text)
        if not match:
            return RubricScore(self.name, 0.0, "fail", f"judge did not emit a score: {result.text[:200]}")
        raw_score = float(match.group(1))
        normalized = max(0.0, min(raw_score / 10.0, 1.0))
        verdict: Verdict = "pass" if normalized >= self.passing_score else "fail"
        return RubricScore(self.name, normalized, verdict, f"judge={raw_score}/10")


# ---------------------------------------------------------------------------
# Suite + runner
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class EvalResult:
    case_id: str
    actual: str
    scores: list[RubricScore]
    weighted_score: float
    verdict: Verdict
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "actual": self.actual,
            "weighted_score": self.weighted_score,
            "verdict": self.verdict,
            "metadata": self.metadata,
            "scores": [
                {
                    "rubric": s.rubric,
                    "score": s.score,
                    "verdict": s.verdict,
                    "detail": s.detail,
                }
                for s in self.scores
            ],
        }


@dataclass(slots=True)
class EvalSuite:
    name: str
    cases: list[EvalCase]
    rubrics: list[Rubric]


@dataclass(slots=True)
class SuiteReport:
    suite_name: str
    results: list[EvalResult]

    @property
    def pass_rate(self) -> float:
        if not self.results:
            return 0.0
        passed = sum(1 for r in self.results if r.verdict == "pass")
        return passed / len(self.results)

    @property
    def mean_score(self) -> float:
        if not self.results:
            return 0.0
        return statistics.fmean(r.weighted_score for r in self.results)

    def as_dict(self) -> dict[str, Any]:
        return {
            "suite": self.suite_name,
            "pass_rate": self.pass_rate,
            "mean_score": self.mean_score,
            "results": [r.as_dict() for r in self.results],
        }

    def write(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.suffix == ".md":
            p.write_text(_render_markdown(self), encoding="utf-8")
        else:
            p.write_text(json.dumps(self.as_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        return p

    def assert_no_regression_against(
        self,
        baseline_path: str | Path,
        *,
        tolerance: float = 0.01,
    ) -> RegressionReport:
        baseline = json.loads(Path(baseline_path).read_text(encoding="utf-8"))
        drop = baseline["mean_score"] - self.mean_score
        regressions = [
            r.case_id
            for r in self.results
            if r.verdict != "pass"
            and any(
                prev["case_id"] == r.case_id and prev["verdict"] == "pass"
                for prev in baseline.get("results", [])
            )
        ]
        report = RegressionReport(
            suite_name=self.suite_name,
            baseline_mean=baseline["mean_score"],
            current_mean=self.mean_score,
            drop=drop,
            tolerance=tolerance,
            regressed_case_ids=regressions,
        )
        if drop > tolerance or regressions:
            raise AssertionError(report.message())
        return report


@dataclass(slots=True)
class RegressionReport:
    suite_name: str
    baseline_mean: float
    current_mean: float
    drop: float
    tolerance: float
    regressed_case_ids: list[str]

    def message(self) -> str:
        return (
            f"Regression detected in suite {self.suite_name!r}: "
            f"mean {self.baseline_mean:.3f} -> {self.current_mean:.3f} "
            f"(drop={self.drop:.3f}, tolerance={self.tolerance:.3f}); "
            f"newly failing cases: {self.regressed_case_ids}"
        )


def _verdict_for(weighted: float, per_rubric: list[RubricScore]) -> Verdict:
    if any(s.verdict == "fail" for s in per_rubric):
        return "fail"
    if all(s.verdict == "skip" for s in per_rubric):
        return "skip"
    return "pass" if weighted >= 0.5 else "fail"


def run_suite(
    suite: EvalSuite,
    *,
    run_one: Callable[[EvalCase], str],
) -> SuiteReport:
    """Execute every case in ``suite`` through ``run_one``.

    ``run_one`` receives the :class:`EvalCase` and returns the text the system
    under test produced. Keeping this callable lets us reuse the framework for
    any recipe without the framework knowing about Claude at all.
    """

    results: list[EvalResult] = []
    total_weight = sum(max(r.weight, 0.0) for r in suite.rubrics) or 1.0
    for case in suite.cases:
        actual = run_one(case)
        per_rubric = [rubric.evaluate(case=case, actual=actual) for rubric in suite.rubrics]
        weighted = sum(
            s.score * rubric.weight
            for s, rubric in zip(per_rubric, suite.rubrics, strict=True)
        ) / total_weight
        verdict = _verdict_for(weighted, per_rubric)
        results.append(
            EvalResult(
                case_id=case.case_id,
                actual=actual,
                scores=per_rubric,
                weighted_score=weighted,
                verdict=verdict,
                metadata=dict(case.metadata),
            )
        )
        logger.info(
            "eval.case",
            extra={"case_id": case.case_id, "verdict": verdict, "score": weighted},
        )
    return SuiteReport(suite_name=suite.name, results=results)


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------


def _render_markdown(report: SuiteReport) -> str:
    lines = [
        f"# Eval report: {report.suite_name}",
        "",
        f"- Cases: {len(report.results)}",
        f"- Pass rate: {report.pass_rate * 100:.1f}%",
        f"- Mean weighted score: {report.mean_score:.3f}",
        "",
        "| Case | Verdict | Score | Rubrics |",
        "| --- | --- | --- | --- |",
    ]
    for r in report.results:
        rubric_cell = "; ".join(f"{s.rubric}={s.score:.2f}" for s in r.scores)
        lines.append(f"| {r.case_id} | {r.verdict} | {r.weighted_score:.3f} | {rubric_cell} |")
    lines.append("")
    return "\n".join(lines)
