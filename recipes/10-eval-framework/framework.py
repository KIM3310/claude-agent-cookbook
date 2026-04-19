"""Recipe 10: the cookbook's standardized eval harness.

This module thinly re-exports :mod:`common.eval` with convenience functions
for typical gold-set flows: loading JSONL files, assembling a default rubric
set for RAG, and writing reports into ``recipes/10-eval-framework/reports/``.

The evaluation framework lives in ``common/`` so every other recipe can
import it without a circular dependency on recipe 10. Recipe 10 is the
public documentation surface.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Iterable
from pathlib import Path

from common.eval import (
    EvalCase,
    EvalResult,
    EvalSuite,
    ExactMatchRubric,
    JSONSchemaRubric,
    JudgeRubric,
    KeywordPresenceRubric,
    NumericToleranceRubric,
    RegressionReport,
    Rubric,
    RubricScore,
    SuiteReport,
    run_suite,
)
from common.logging import get_logger, setup_logging

from .rubrics import (
    FaithfulnessRubric,
    GroundednessRubric,
    LabelConfusionRubric,
    StructureRubric,
)

logger = get_logger(__name__)

REPORTS_DIR = Path(__file__).parent / "reports"
DEFAULT_GOLD_SET = Path(__file__).parent / "example_gold_set.jsonl"


# ---------------------------------------------------------------------------
# Gold-set loading
# ---------------------------------------------------------------------------


def load_gold_set(path: Path) -> list[EvalCase]:
    """Load cases from a JSONL file. Each row must be valid against :class:`EvalCase`."""
    cases: list[EvalCase] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        cases.append(EvalCase.from_dict(json.loads(line)))
    return cases


# ---------------------------------------------------------------------------
# Canned rubric bundles
# ---------------------------------------------------------------------------


def default_rag_rubrics(*, retrieved_keyword: str | None = None) -> list[Rubric]:
    """Rubrics useful for grading RAG pipelines."""
    rubrics: list[Rubric] = [FaithfulnessRubric(), GroundednessRubric()]
    if retrieved_keyword:
        rubrics.append(KeywordPresenceRubric([retrieved_keyword]))
    return rubrics


def default_classification_rubrics() -> list[Rubric]:
    return [LabelConfusionRubric()]


def default_structured_output_rubrics(required_keys: Iterable[str]) -> list[Rubric]:
    return [JSONSchemaRubric(list(required_keys))]


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def evaluate(
    *,
    suite: EvalSuite,
    run_one: Callable[[EvalCase], str],
    baseline_path: Path | None = None,
    report_path: Path | None = None,
    regression_tolerance: float = 0.01,
) -> tuple[SuiteReport, RegressionReport | None]:
    """Run the suite, write a report, optionally check for regressions.

    Returns ``(report, regression_report)`` where ``regression_report`` is
    ``None`` when no baseline was supplied.
    """
    report = run_suite(suite, run_one=run_one)
    if report_path is not None:
        report.write(report_path)
        logger.info(
            "eval.report_written",
            extra={"path": str(report_path), "mean_score": report.mean_score},
        )
    regression: RegressionReport | None = None
    if baseline_path is not None and baseline_path.exists():
        regression = report.assert_no_regression_against(baseline_path, tolerance=regression_tolerance)
    return report, regression


# ---------------------------------------------------------------------------
# Example runner (CLI)
# ---------------------------------------------------------------------------


def _example_run_one(case: EvalCase) -> str:
    """Deterministic "system under test" for the shipped example suite.

    Used by the CLI so `python recipes/10-eval-framework/framework.py` runs
    without an API key. Real recipes would pass their own `run_one`.
    """
    expected = case.expected
    if isinstance(expected, str):
        return expected
    if isinstance(expected, (int, float)):
        return f"The answer is {expected}."
    return ""


def _cli() -> int:
    parser = argparse.ArgumentParser(description="Recipe 10 — eval framework example run")
    parser.add_argument("--gold-set", type=Path, default=DEFAULT_GOLD_SET)
    parser.add_argument("--report", type=Path, default=REPORTS_DIR / "latest.md")
    parser.add_argument("--baseline", type=Path, default=None)
    args = parser.parse_args()

    setup_logging()
    cases = load_gold_set(args.gold_set)
    rubrics: list[Rubric] = [ExactMatchRubric(), NumericToleranceRubric(tolerance=0.5)]
    suite = EvalSuite(name="example", cases=cases, rubrics=rubrics)
    report, regression = evaluate(
        suite=suite,
        run_one=_example_run_one,
        report_path=args.report,
        baseline_path=args.baseline,
    )
    summary = {
        "suite": report.suite_name,
        "pass_rate": report.pass_rate,
        "mean_score": report.mean_score,
        "regression": None if regression is None else regression.__dict__,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


__all__ = [
    # re-exports
    "EvalCase",
    "EvalResult",
    "EvalSuite",
    "ExactMatchRubric",
    "JSONSchemaRubric",
    "JudgeRubric",
    "KeywordPresenceRubric",
    "NumericToleranceRubric",
    "RegressionReport",
    "Rubric",
    "RubricScore",
    "SuiteReport",
    "run_suite",
    # recipe 10 additions
    "FaithfulnessRubric",
    "GroundednessRubric",
    "LabelConfusionRubric",
    "StructureRubric",
    # helpers
    "load_gold_set",
    "default_rag_rubrics",
    "default_classification_rubrics",
    "default_structured_output_rubrics",
    "evaluate",
]


if __name__ == "__main__":
    sys.exit(_cli())
