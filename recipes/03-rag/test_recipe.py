"""Tests for recipe 03."""

from __future__ import annotations

from unittest.mock import MagicMock

from common.client import CookbookClient
from recipes._fixtures import FakeTextBlock, FakeUsage, build_response

from .recipe import (
    BM25Retriever,
    answer_query,
    format_context,
    load_corpus,
    parse_citations,
)


def _client(*responses: object) -> CookbookClient:
    raw = MagicMock()
    raw.messages.create.side_effect = list(responses)
    return CookbookClient.with_raw_client(raw)


def test_load_corpus_reads_markdown_files() -> None:
    docs = load_corpus()
    assert len(docs) >= 5
    ids = {d.doc_id for d in docs}
    assert "02_prompt_caching" in ids
    assert all(d.text for d in docs)


def test_retriever_ranks_prompt_caching_for_caching_query() -> None:
    retriever = BM25Retriever(load_corpus())
    hits = retriever.retrieve("How does prompt caching affect cost?", top_k=3)
    hit_ids = [doc.doc_id for doc, _ in hits]
    assert hit_ids[0] == "02_prompt_caching"


def test_retriever_prefers_streaming_for_streaming_query() -> None:
    retriever = BM25Retriever(load_corpus())
    hits = retriever.retrieve("How do I stream tokens and cancel a request?", top_k=2)
    hit_ids = {doc.doc_id for doc, _ in hits}
    assert "07_streaming" in hit_ids


def test_format_context_wraps_documents_in_tags() -> None:
    retriever = BM25Retriever(load_corpus())
    hits = retriever.retrieve("prompt caching", top_k=1)
    block = format_context(hits)
    assert block.startswith('<doc id="')
    assert "</doc>" in block


def test_parse_citations_extracts_doc_ids() -> None:
    text = (
        "Caching reduces cost [doc:02_prompt_caching]. Streaming helps UX "
        "[doc:07_streaming]."
    )
    assert parse_citations(text) == ["02_prompt_caching", "07_streaming"]


def test_answer_query_returns_structured_result() -> None:
    answer = (
        "Prompt caching reduces per-token price on cached input "
        "[doc:02_prompt_caching]."
    )
    response = build_response(
        content=[FakeTextBlock(answer)],
        usage=FakeUsage(200, 60),
        stop_reason="end_turn",
    )
    client = _client(response)
    retriever = BM25Retriever(load_corpus())
    result = answer_query(
        "How does prompt caching affect cost?",
        client=client,
        retriever=retriever,
        top_k=3,
    )
    assert result.citations == ["02_prompt_caching"]
    assert result.citation_coverage == 1.0
    assert result.hits[0]["doc_id"] == "02_prompt_caching"


def test_answer_query_flags_invalid_citations_via_coverage() -> None:
    # Claude emits a citation that isn't in the retrieved set
    answer = "Caching is great [doc:99_fabricated]."
    response = build_response(
        content=[FakeTextBlock(answer)],
        usage=FakeUsage(200, 30),
        stop_reason="end_turn",
    )
    client = _client(response)
    retriever = BM25Retriever(load_corpus())
    result = answer_query(
        "caching?",
        client=client,
        retriever=retriever,
        top_k=2,
    )
    assert result.citations == ["99_fabricated"]
    assert result.citation_coverage == 0.0
