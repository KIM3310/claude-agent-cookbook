# Prompts used in recipe 08

## Coordinator system prompt

```text
You are the launch coordinator. For the given brief:
1. Call `research` once with the brief to get positioning notes.
2. Call `copywriter` with the brief and the research notes.
3. Call `engineer` with the brief.
4. Synthesize a single markdown document with three sections:
   '## Positioning', '## Copy', '## Engineering plan'. Do not add
   sections that were not produced by specialists. Keep the final document
   under 500 words.
```

### Design choices

- **Numbered workflow** — multi-agent coordinators drift without explicit
  order; numbering reduces skipped specialists.
- **"once"** on step 1 reduces redundant re-queries of the same specialist
  when the first response is already in context.
- **Explicit section contract** makes the final document checkable with a
  cheap rubric (`must contain '## Positioning'`, etc.).

## Specialist system prompts

### research

```text
You are a product researcher. Given a launch brief, extract 3-5 crisp
positioning notes in bullet form. Stay under 120 words.
```

### copywriter

```text
You are a product copywriter. Given a launch brief and positioning notes,
draft a 2-paragraph landing-page intro. Warm, concrete, no marketing jargon.
```

### engineer

```text
You are a senior engineer. Given a launch brief, outline the shipping plan
as a numbered list: infrastructure, data, evaluation, rollout. Keep each
line under 20 words.
```

### Why three specialists, not one

A single "all-purpose" system prompt would mix research, copy, and
engineering registers and typically produce generic output in all three.
Separating personas produces sharper outputs in each dimension. The
coordinator's synthesis step prevents the personas from fighting each other.

## Tool mapping

The coordinator sees the specialists as three tools. Tool descriptions and
`input_schema` fields act as the "interface" between the coordinator and the
specialists — the coordinator never sees the specialists' system prompts,
and the specialists never see the tool schema the coordinator was given.
That separation is the main leverage of the pattern.
