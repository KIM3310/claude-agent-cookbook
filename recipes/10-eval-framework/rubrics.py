"""Domain-specific rubrics reused across the cookbook.

These extend :mod:`common.eval` with patterns specifically useful for RAG
and agentic pipelines.
"""

from __future__ import annotations

import re
from typing import Any

from common.eval import EvalCase, Rubric, RubricScore


class FaithfulnessRubric(Rubric):
    """Score: fraction of cited doc ids that appear in the retrieved set.

    The system under test is expected to return a dict (or stringified
    JSON) containing ``citations`` (list of ids) and ``hits`` (list of
    dicts with ``doc_id`` keys). This rubric measures whether the citations
    claim to come from documents that were actually retrieved. Low scores
    indicate fabrication.
    """

    name = "faithfulness"

    def evaluate(self, *, case: EvalCase, actual: str) -> RubricScore:
        # Accept either a JSON-serialized payload or plain text with bracket citations.
        doc_ids_retrieved = set(case.metadata.get("retrieved_doc_ids", []))
        citations = _parse_any_citations(actual)
        if not citations:
            return RubricScore(self.name, 0.0, "fail", "no citations found in answer")
        valid = [c for c in citations if c in doc_ids_retrieved]
        score = len(valid) / len(citations)
        verdict: str = "pass" if score >= 0.5 else "fail"
        detail = f"valid_citations={len(valid)}/{len(citations)}"
        return RubricScore(self.name, score, verdict, detail)  # type: ignore[arg-type]


_CITATION_RE = re.compile(r"\[doc:([A-Za-z0-9_-]+)\]")


def _parse_any_citations(text: str) -> list[str]:
    return _CITATION_RE.findall(text)


class GroundednessRubric(Rubric):
    """Measures whether the answer's claims appear (by overlap) in retrieved context.

    This is a cheap deterministic heuristic that works well as a filter.
    For high-stakes applications, pair it with a JudgeRubric.
    """

    name = "groundedness"
    _WORD_RE = re.compile(r"[A-Za-z0-9]{4,}")

    def evaluate(self, *, case: EvalCase, actual: str) -> RubricScore:
        context: str = str(case.metadata.get("context", ""))
        if not context:
            return RubricScore(self.name, 0.0, "skip", "no context supplied in case.metadata.context")
        actual_words = {w.lower() for w in self._WORD_RE.findall(actual)}
        context_words = {w.lower() for w in self._WORD_RE.findall(context)}
        # Strip trivial stopwords by filtering by length above
        if not actual_words:
            return RubricScore(self.name, 0.0, "fail", "empty answer")
        overlap = actual_words & context_words
        score = len(overlap) / len(actual_words)
        verdict: str = "pass" if score >= 0.4 else "fail"
        return RubricScore(self.name, score, verdict, f"overlap={len(overlap)}/{len(actual_words)}")  # type: ignore[arg-type]


class LabelConfusionRubric(Rubric):
    """Exact-label check for classification tasks.

    ``case.expected`` is the label string, ``actual`` is the model's output.
    Case-insensitive, whitespace-tolerant, tolerates punctuation.
    """

    name = "label_confusion"
    _CLEAN_RE = re.compile(r"[^A-Za-z0-9]+")

    def evaluate(self, *, case: EvalCase, actual: str) -> RubricScore:
        expected = str(case.expected or "")
        a = self._CLEAN_RE.sub("", actual).lower()
        e = self._CLEAN_RE.sub("", expected).lower()
        ok = a == e
        return RubricScore(
            self.name,
            1.0 if ok else 0.0,
            "pass" if ok else "fail",
            f"expected={e!r} actual={a!r}",
        )


class StructureRubric(Rubric):
    """Measures how many required headings/sections appear in an answer.

    Useful for multi-agent outputs where the coordinator is required to
    assemble a specific document structure (see recipe 08).
    """

    name = "structure"

    def __init__(self, required_markers: list[str]) -> None:
        self.required_markers = required_markers

    def evaluate(self, *, case: EvalCase, actual: str) -> RubricScore:
        if not self.required_markers:
            return RubricScore(self.name, 1.0, "pass", "no markers configured")
        hits = [m for m in self.required_markers if m in actual]
        score = len(hits) / len(self.required_markers)
        verdict = "pass" if score >= 0.99 else "fail"
        return RubricScore(
            self.name,
            score,
            verdict,  # type: ignore[arg-type]
            f"hits={hits} missing={[m for m in self.required_markers if m not in hits]}",
        )


__all__ = [
    "FaithfulnessRubric",
    "GroundednessRubric",
    "LabelConfusionRubric",
    "StructureRubric",
]
