"""Recipe 03: retrieval-augmented generation with citations.

We use BM25 over a small local corpus to keep the recipe dependency-light. The
same pattern works with any retriever — swap ``BM25Retriever`` for an
embedding-based implementation and the surrounding code is unchanged.

The interesting part is the prompt contract: we instruct Claude to cite each
claim with the document id of the passage that supports it, and we wrap
retrieved passages in ``<doc id="...">`` tags so citations are unambiguous.
The returned payload parses citations back out of the response for
programmatic consumers (for instance, the eval framework's faithfulness
rubric).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rank_bm25 import BM25Okapi

from common.client import CookbookClient
from common.logging import get_logger, setup_logging

logger = get_logger(__name__)

CORPUS_DIR = Path(__file__).parent / "corpus"

SYSTEM_PROMPT = (
    "You are a documentation assistant that answers questions from a supplied "
    "set of passages. Always cite the passage id for every factual claim "
    "using the format [doc:ID] immediately after the claim. If the passages "
    "do not answer the question, say so explicitly and do not fabricate. "
    "Keep answers to at most three sentences."
)


# ---------------------------------------------------------------------------
# Corpus loading & retrieval
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Document:
    doc_id: str
    title: str
    text: str


def load_corpus(directory: Path = CORPUS_DIR) -> list[Document]:
    docs: list[Document] = []
    for path in sorted(directory.glob("*.md")):
        body = path.read_text(encoding="utf-8").strip()
        title = body.splitlines()[0].lstrip("# ").strip() if body else path.stem
        docs.append(Document(doc_id=path.stem, title=title, text=body))
    return docs


_TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_-]*")


def _tokenize(text: str) -> list[str]:
    return [tok.lower() for tok in _TOKEN_RE.findall(text)]


class BM25Retriever:
    """Thin BM25 wrapper over a list of documents."""

    def __init__(self, documents: list[Document]) -> None:
        if not documents:
            raise ValueError("corpus is empty")
        self.documents = documents
        self._bm25 = BM25Okapi([_tokenize(d.text) for d in documents])

    def retrieve(self, query: str, *, top_k: int = 3) -> list[tuple[Document, float]]:
        scores = self._bm25.get_scores(_tokenize(query))
        ranked_indices = sorted(range(len(scores)), key=lambda i: -scores[i])[:top_k]
        return [(self.documents[i], float(scores[i])) for i in ranked_indices]


# ---------------------------------------------------------------------------
# Prompt assembly + citation parsing
# ---------------------------------------------------------------------------


def format_context(hits: list[tuple[Document, float]]) -> str:
    parts: list[str] = []
    for doc, score in hits:
        parts.append(
            f'<doc id="{doc.doc_id}" title="{doc.title}" score="{score:.3f}">\n'
            f"{doc.text}\n"
            f"</doc>"
        )
    return "\n\n".join(parts)


_CITATION_RE = re.compile(r"\[doc:([A-Za-z0-9_-]+)\]")


def parse_citations(text: str) -> list[str]:
    """Return every ``[doc:ID]`` citation found in ``text`` in order."""
    return _CITATION_RE.findall(text)


# ---------------------------------------------------------------------------
# End-to-end RAG pipeline
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class RAGResult:
    query: str
    hits: list[dict[str, Any]]
    answer: str
    citations: list[str]
    citation_coverage: float
    usage: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "hits": self.hits,
            "answer": self.answer,
            "citations": self.citations,
            "citation_coverage": self.citation_coverage,
            "usage": self.usage,
        }


def answer_query(
    query: str,
    *,
    client: CookbookClient,
    retriever: BM25Retriever,
    top_k: int = 3,
) -> RAGResult:
    hits = retriever.retrieve(query, top_k=top_k)
    context = format_context(hits)
    user_message = (
        f"Passages:\n{context}\n\n"
        f"Question: {query}\n"
        "Answer with citations in [doc:ID] form after each claim."
    )

    response = client.create_message(
        messages=[{"role": "user", "content": user_message}],
        system=SYSTEM_PROMPT,
        max_tokens=512,
    )

    citations = parse_citations(response.text)
    hit_ids = {doc.doc_id for doc, _ in hits}
    valid_citations = [c for c in citations if c in hit_ids]
    coverage = len(valid_citations) / max(len(citations), 1) if citations else 0.0

    return RAGResult(
        query=query,
        hits=[
            {"doc_id": doc.doc_id, "title": doc.title, "score": score}
            for doc, score in hits
        ],
        answer=response.text,
        citations=citations,
        citation_coverage=coverage,
        usage=client.ledger.summary(),
    )


def _cli() -> int:
    parser = argparse.ArgumentParser(description="Recipe 03 — RAG with citations")
    parser.add_argument("--query", default="How does prompt caching affect cost?")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    setup_logging()
    client = CookbookClient()
    retriever = BM25Retriever(load_corpus())
    result = answer_query(args.query, client=client, retriever=retriever, top_k=args.top_k)
    rendered = json.dumps(result.as_dict(), indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
