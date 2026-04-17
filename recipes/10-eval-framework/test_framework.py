"""Tests for recipe 10."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from common.eval import EvalCase, EvalSuite
from common.types import CompletionResult

from .framework import (
    DEFAULT_GOLD_SET,
    default_classification_rubrics,
    default_rag_rubrics,
    default_structured_output_rubrics,
    evaluate,
    load_gold_set,
)
from .rubrics import (
    FaithfulnessRubric,
    GroundednessRubric,
    LabelConfusionRubric,
    StructureRubric,
)


def test_shipped_gold_set_parses() -> None:
    cases = load_gold_set(DEFAULT_GOLD_SET)
    assert len(cases) == 20
    assert all(c.case_id for c in cases)


def test_faithfulness_rubric_passes_when_all_citations_are_retrieved() -> None:
    case = EvalCase(
        case_id="c1",
        prompt="q",
        expected=None,
        metadata={"retrieved_doc_ids": ["a", "b", "c"]},
    )
    score = FaithfulnessRubric().evaluate(case=case, actual="Caching is great [doc:a].")
    assert score.verdict == "pass"
    assert score.score == 1.0


def test_faithfulness_rubric_fails_on_fabricated_citation() -> None:
    case = EvalCase(
        case_id="c1",
        prompt="q",
        expected=None,
        metadata={"retrieved_doc_ids": ["a", "b"]},
    )
    score = FaithfulnessRubric().evaluate(case=case, actual="Some claim [doc:z].")
    assert score.verdict == "fail"
    assert score.score == 0.0


def test_faithfulness_rubric_fails_when_no_citations() -> None:
    case = EvalCase(case_id="c1", prompt="q", expected=None, metadata={"retrieved_doc_ids": ["a"]})
    score = FaithfulnessRubric().evaluate(case=case, actual="No citations here.")
    assert score.verdict == "fail"


def test_groundedness_rubric_rewards_overlap() -> None:
    case = EvalCase(
        case_id="c1",
        prompt="q",
        expected=None,
        metadata={
            "context": "Prompt caching charges a premium on cache creation and discounts cache reads.",
        },
    )
    high = GroundednessRubric().evaluate(
        case=case,
        actual="Caching applies a premium on creation and discounts on reads.",
    )
    low = GroundednessRubric().evaluate(
        case=case,
        actual="Unicorns generally prefer rainbows and sparkles everywhere.",
    )
    assert high.score > low.score
    assert low.verdict == "fail"


def test_groundedness_skips_without_context() -> None:
    case = EvalCase(case_id="c1", prompt="q")
    score = GroundednessRubric().evaluate(case=case, actual="anything")
    assert score.verdict == "skip"


def test_label_confusion_is_punctuation_insensitive() -> None:
    case = EvalCase(case_id="c1", prompt="p", expected="positive")
    good = LabelConfusionRubric().evaluate(case=case, actual="POSITIVE.")
    bad = LabelConfusionRubric().evaluate(case=case, actual="Very positive indeed")
    assert good.verdict == "pass"
    assert bad.verdict == "fail"


def test_structure_rubric_checks_all_required_markers() -> None:
    rubric = StructureRubric(["## Positioning", "## Copy", "## Engineering plan"])
    good = rubric.evaluate(
        case=EvalCase(case_id="c1", prompt="p"),
        actual="## Positioning\n## Copy\n## Engineering plan\n",
    )
    bad = rubric.evaluate(
        case=EvalCase(case_id="c1", prompt="p"),
        actual="## Positioning\n(missing the others)",
    )
    assert good.verdict == "pass"
    assert bad.verdict == "fail"


def test_default_rubric_bundles_return_expected_types() -> None:
    rag = default_rag_rubrics()
    assert {r.name for r in rag} >= {"faithfulness", "groundedness"}
    cls = default_classification_rubrics()
    assert any(r.name == "label_confusion" for r in cls)
    extract = default_structured_output_rubrics(["vendor", "total"])
    assert extract[0].name == "json_schema"


def test_evaluate_writes_report_and_detects_regression(tmp_path: Path) -> None:
    cases = [
        EvalCase(case_id="c1", prompt="q", expected="hello"),
        EvalCase(case_id="c2", prompt="q", expected="world"),
    ]
    suite = EvalSuite(
        name="demo",
        cases=cases,
        rubrics=[LabelConfusionRubric()],
    )

    good = lambda c: str(c.expected)  # noqa: E731
    baseline_report, _ = evaluate(
        suite=suite,
        run_one=good,
        report_path=tmp_path / "baseline.json",
    )
    assert baseline_report.pass_rate == 1.0

    regressed = lambda c: "wrong"  # noqa: E731
    suite2 = EvalSuite(name="demo", cases=cases, rubrics=[LabelConfusionRubric()])
    with pytest.raises(AssertionError):
        evaluate(
            suite=suite2,
            run_one=regressed,
            report_path=tmp_path / "current.json",
            baseline_path=tmp_path / "baseline.json",
        )


def test_evaluate_with_judge_rubric_via_mocked_client() -> None:
    judge = MagicMock()
    judge.create_message.return_value = CompletionResult(
        text="9\nBreakdown: correct entity and correct number.",
        stop_reason="end_turn",
        input_tokens=0,
        output_tokens=0,
    )
    from common.eval import JudgeRubric

    case = EvalCase(case_id="c1", prompt="how much?", expected="$100")
    rubric = JudgeRubric(judge_client=judge, passing_score=0.7)
    score = rubric.evaluate(case=case, actual="About one hundred dollars.")
    assert score.verdict == "pass"
    assert score.score == pytest.approx(0.9)
