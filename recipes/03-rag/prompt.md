# Prompts used in recipe 03

## System prompt

```text
You are a documentation assistant that answers questions from a supplied set
of passages. Always cite the passage id for every factual claim using the
format [doc:ID] immediately after the claim. If the passages do not answer
the question, say so explicitly and do not fabricate. Keep answers to at
most three sentences.
```

### Rationale

- **Explicit citation format.** `[doc:ID]` is trivial to parse and verify;
  prose citations like "see the caching doc" are not. A regex plus
  retrieved-hit membership gives us a cheap faithfulness signal.
- **Failure instruction.** "Do not fabricate" reduces the most common RAG
  failure mode: confabulation when the retriever misses. Paired with the
  explicit "say so" clause, Claude answers honestly when passages are
  off-topic.
- **Length cap.** Three-sentence answers are long enough to include citations
  but short enough that drift is limited.

## User-message template

```text
Passages:
<doc id="..." title="..." score="...">
...
</doc>

Question: {user question}
Answer with citations in [doc:ID] form after each claim.
```

### Why XML-ish tags

Claude has been trained to follow structured document blocks well. Wrapping
passages in `<doc>` tags with id and title attributes gives Claude a clear
delimiter between source material and the question, and makes the
instruction "cite the passage id" concretely grounded in the visible tags.
