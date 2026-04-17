"""Tests for :mod:`common.eval`."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from common.eval import (
    EvalCase,
    EvalSuite,
    ExactMatchRubric,
    JSONSchemaRubric,
    JudgeRubric,
    KeywordPresenceRubric,
    NumericToleranceRubric,
    run_suite,
)
from common.types import CompletionResult


def test_keyword_presence_counts_matches() -> None:
    rubric = KeywordPresenceRubric(["alpha", "beta", "gamma"])
    score = rubric.evaluate(
        case=EvalCase(case_id="c1", prompt="", expected=None),
        actual="The alpha and GAMMA arrived",
    )
    assert score.score == pytest.approx(2 / 3)
    assert score.verdict == "pass"


def test_exact_match_rubric_passes_on_strip() -> None:
    rubric = ExactMatchRubric()
    case = EvalCase(case_id="c1", prompt="", expected="  hello ")
    assert rubric.evaluate(case=case, actual="hello").verdict == "pass"
    assert rubric.evaluate(case=case, actual="hello world").verdict == "fail"


def test_json_schema_rubric_checks_required_keys() -> None:
    rubric = JSONSchemaRubric(["vendor", "total"])
    case = EvalCase(case_id="c1", prompt="", expected=None)
    passing = rubric.evaluate(
        case=case,
        actual=json.dumps({"vendor": "Acme", "total": 42.0, "extra": 1}),
    )
    assert passing.verdict == "pass"
    missing = rubric.evaluate(case=case, actual=json.dumps({"vendor": "Acme"}))
    assert missing.verdict == "fail"
    assert "total" in missing.detail
    broken = rubric.evaluate(case=case, actual="not json")
    assert broken.verdict == "fail"


def test_numeric_tolerance_passes_and_fails() -> None:
    rubric = NumericToleranceRubric(tolerance=0.05)
    case = EvalCase(case_id="c1", prompt="", expected=3.14)
    assert rubric.evaluate(case=case, actual="the answer is 3.15").verdict == "pass"
    assert rubric.evaluate(case=case, actual="the answer is 4.0").verdict == "fail"
    assert rubric.evaluate(case=case, actual="no numbers here").verdict == "fail"


def test_judge_rubric_parses_first_line_score() -> None:
    judge_client = MagicMock()
    judge_client.create_message.return_value = CompletionResult(
        text="8.5\nThis answer covers the main points but misses one citation.",
        stop_reason="end_turn",
        input_tokens=0,
        output_tokens=0,
    )
    rubric = JudgeRubric(judge_client=judge_client, passing_score=0.7)
    score = rubric.evaluate(
        case=EvalCase(case_id="c1", prompt="q?", expected="a"),
        actual="candidate answer",
    )
    assert score.score == pytest.approx(0.85)
    assert score.verdict == "pass"


def test_run_suite_computes_weighted_score_and_verdict() -> None:
    suite = EvalSuite(
        name="demo",
        cases=[
            EvalCase(case_id="c1", prompt="greet", expected="hello"),
            EvalCase(case_id="c2", prompt="greet", expected="hello"),
        ],
        rubrics=[ExactMatchRubric(), KeywordPresenceRubric(["hello"])],
    )

    def run_one(case: EvalCase) -> str:
        return "hello" if case.case_id == "c1" else "hi"

    report = run_suite(suite, run_one=run_one)
    assert report.pass_rate == 0.5
    c1, c2 = report.results
    assert c1.verdict == "pass"
    assert c2.verdict == "fail"
    assert c1.weighted_score == pytest.approx(1.0)


def test_report_write_and_regression_detection(tmp_path: Path) -> None:
    suite = EvalSuite(
        name="demo",
        cases=[EvalCase(case_id="c1", prompt="q", expected="a")],
        rubrics=[ExactMatchRubric()],
    )
    baseline_report = run_suite(suite, run_one=lambda _c: "a")
    baseline_path = tmp_path / "baseline.json"
    baseline_report.write(baseline_path)

    # Same run should not regress
    baseline_report.assert_no_regression_against(baseline_path)

    # Regressed run
    current_report = run_suite(suite, run_one=lambda _c: "b")
    with pytest.raises(AssertionError) as excinfo:
        current_report.assert_no_regression_against(baseline_path)
    assert "c1" in str(excinfo.value)


def test_report_markdown_write(tmp_path: Path) -> None:
    suite = EvalSuite(
        name="demo",
        cases=[EvalCase(case_id="c1", prompt="q", expected="a")],
        rubrics=[ExactMatchRubric()],
    )
    report = run_suite(suite, run_one=lambda _c: "a")
    md_path = tmp_path / "out.md"
    report.write(md_path)
    content = md_path.read_text(encoding="utf-8")
    assert "Eval report" in content
    assert "| c1 |" in content
    assert "pass" in content.lower()


def test_eval_case_from_dict_roundtrip() -> None:
    case = EvalCase.from_dict(
        {"case_id": "c1", "prompt": "q", "expected": "a", "metadata": {"topic": "x"}}
    )
    assert case.case_id == "c1"
    assert case.metadata == {"topic": "x"}
