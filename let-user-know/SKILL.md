---
name: let-user-know
description: Use when the user asks what this window just did, what went wrong or how it was resolved, wants a plain-language recap of recent progress or process, asks where its specs, plans, plan_ref, or artifacts are, or wants session-specific workflow terms explained.
---

# let user know

## Overview

This skill helps the user understand the current window in plain language.

Use it to translate agent work into:

- what happened
- how the important work happened when the user asks for process
- what material problem, blocker, or unexpected result occurred and how it was handled
- why it mattered
- what the terms in the updates meant

Treat "this window" as the full logical conversation, including work preserved in
context-compaction or continuation summaries. A compaction boundary is not the
start of a new window.

## When To Use

Use this skill when the user asks things like:

- 这个窗口刚刚干了什么
- 你刚刚在汇报里说的那些名词是什么意思
- 用白话解释一下你在做什么
- 帮我总结这轮做了什么，以及我该怎么理解
- 之前 optimization 的过程没给我
- 刚才这个 skill 是怎么优化的

This skill can also trigger passively when the user is clearly confused by progress updates, workflow terms, or agent jargon.

Do not use this skill for deep architectural teaching, broad project onboarding, or generic glossary generation unrelated to the current session.

## Workflow

### 1. Reconstruct The Window

First identify the smallest truthful story of the full logical window.

Before drafting, inspect every available session source:

1. context-compaction, continuation, or previous-model summaries
2. visible messages before and after the latest summary
3. current tool/subagent state and repository evidence when they were part of the session

Build a private coverage inventory with three buckets:

- material work completed before compaction
- work completed after compaction
- current result, blocker, or next step

For every material problem, blocker, regression, or unexpected result recovered
from any of those sources, also record a user-facing resolution chain:

- problem: the observed symptom and where it occurred
- cause or diagnosis: only when supported by evidence; otherwise say what is still uncertain
- handling: the concrete corrective action, investigation, or decision taken
- outcome: the validation result, remaining blocker, or reason it is still unresolved

Do not infer a root cause merely because a later edit made the symptom disappear.
If the same issue appears in both compressed and visible context, merge it into
one chain and let newer live evidence determine its current outcome.

For a repository-backed task, also build a small artifact provenance inventory:

- task-specific `spec` files
- selected plan files or approved `plan_ref`
- task contract or workflow artifact when no plan file exists
- whether each artifact was created, reused, only referenced, or missing

Verify paths from the session and current repository when practical. Prefer an
explicit `plan_ref`, committed/changed files, and exact task-id or title matches.
A file that merely mentions the task is not automatically its spec or plan.

Deduplicate facts repeated by a summary and later messages. Prefer current code,
tests, tool state, and newer evidence when a summary is stale or contradicted.
Do not omit material work merely because it is only present in compressed context.

Then identify:

- the user's goal
- what prompted the latest recap or optimization
- the main actions the agent actually took
- the current result or status
- any blocker or uncertainty still present
- the material problems encountered, how they were handled, and their outcomes
- the exact paths of any corresponding spec and plan artifacts

Prefer the most recent and relevant actions. Do not turn every shell read or tiny intermediate step into the main story.

If compressed context contains a substantial part of the work, either:

- integrate it into the main chronological recap, or
- split the recap into `压缩前的主要进展` and `压缩后的工作` when that makes the history clearer.

Do not describe compaction as work the agent performed. It is only a storage
boundary for earlier work. When useful for transparency, say that an item was
recovered from the compressed session summary.

When a material problem or its handling exists only in compressed context,
include it in the recap. Do not reduce it to a generic phrase such as
"handled an issue" or omit it because the later visible messages only show a
handoff, commit, or next step.

### Reference Examples

Read [references/examples.md](references/examples.md) when any of these is true:

- a compaction, continuation, or previous-model summary is present
- the user says earlier work or process was omitted
- compressed context conflicts with newer tool or repository evidence

Use the examples as coverage and truthfulness guides, not as fixed wording.

### 2. Add Process Trace When Needed

If the user says the process was missing, asks how an optimization happened, or challenges an earlier recap as too result-only, include a short process trace before term explanations.

Use 4 to 7 concrete steps:

- trigger: what user request or observed gap started the work
- context read: which files, skill docs, repo rules, or evidence shaped the change
- decision: what design choice was made and why
- edit: what changed at a high level, with paths when useful
- validation: what was actually checked
- status: what remains uncommitted, risky, blocked, or intentionally out of scope

Keep this as a causal story, not a shell log. Say "I did not do X" when the user might reasonably infer it but it did not happen.

### 3. Extract The Terms That Need Translation

If the user named terms explicitly, explain those first.

Otherwise, extract the 3 to 7 most important terms from recent updates, such as:

- skill names
- workflow labels
- validation terms
- repo-specific process words
- tool names only if they mattered to the outcome

Ignore routine noise unless it affected what happened.

### 4. Explain Each Term In Context

For each term, explain:

1. what it means in simple language
2. why it came up in this window
3. whether it changed what the agent did

Keep explanations concrete. Prefer:

- `Lite`: a low-risk path for small local edits

over:

- `Lite`: one of several workflow lanes in the repository control plane

If a term is repo-specific, say so.

## Output Shape

Default to these parts in this order:

### 1. 这窗口刚刚做了什么

Use 3 to 6 short bullets or a short paragraph that covers:

- goal
- main actions
- current state

### 2. 遇到的问题与处理

Include this whenever the window contains a material problem, blocker,
regression, failed validation, or unexpected result. This is required even if
the relevant evidence appears only in compressed context.

Use 2 to 4 concise bullets that make the causal chain visible:

- `问题`: what failed, was blocked, or was unexpectedly observed
- `处理`: how it was diagnosed or corrected; name the evidence when it matters
- `结果`: what validation proved, what remains unresolved, or why no resolution was attempted

Do not claim a cause, fix, or validation that did not actually happen. If the
problem remains open, say so directly instead of implying that an investigation
or handoff resolved it. Omit this section only when there was no material issue.

### 3. 规格与计划

Include this whenever the task has a corresponding `spec`, plan file, approved
`plan_ref`, or task contract, even if the user only asks for a short recap.
Give exact paths and say whether each artifact was created for this task or
reused. If the user explicitly asks where they are and none exists, say so;
distinguish a session-only `update_plan` from a durable repository plan.

For a one-sentence answer, fold this provenance into that sentence instead of
dropping it.

### 4. 刚才的过程

Only include this when the user asks for the missing process, optimization trace, or "how did we get here".

Use short bullets that cover:

- why the work started
- what evidence or files were read
- what decision changed the skill behavior
- what was edited and verified
- what was not done

### 5. 名词解释

Explain each important term in plain language. If process is the user's main ask, keep this section shorter than the process trace.

For each term, use this shape:

- `term`: simple meaning in this window, plus why it mattered here

### 6. 还没完成的部分

Only include this when there is real unfinished work, risk, or uncertainty.

## Hard Rules

- Do not treat the most recent compaction boundary as the beginning of "this window".
- Do not answer from visible post-compaction messages alone when a compaction or continuation summary is available.
- Do not double-count work repeated in both compressed context and visible messages.
- Do not omit a material compressed-context problem, its supported diagnosis, the action taken, or its verified outcome just because later visible messages contain only a handoff, commit, or status update.
- Do not turn an unresolved issue into a resolved one by describing investigation, a workaround, or a handoff as a fix.
- Do not present correlation as a root cause; distinguish observed symptom, evidence-backed diagnosis, corrective action, and validation result.
- If compressed context and live repository evidence conflict, report the current verified state and briefly note the stale summary.
- Do not pretend the agent completed work it only planned.
- Do not omit an existing task-specific spec or selected plan because the user requested brevity.
- Do not invent a spec or plan, and do not relabel evidence, an optimization case, a handoff, or an internal `update_plan` as a durable plan.
- Distinguish a task-specific plan from a general lane plan and from an unrelated plan that only mentions the task.
- When the user asks for artifact locations, report missing artifacts as a workflow gap instead of silently substituting the nearest file.
- Do not dump raw command logs unless the user asked for them.
- Do not replace a requested process recap with only outcomes or glossary terms.
- Do not invent a process step from intention; only include actions that actually happened.
- Do not explain terms in the abstract if this window gives a more useful concrete meaning.
- Do not overload the answer with every possible term; include only the ones that help the user understand this session.
- If the window does not provide enough evidence for a term, say that plainly instead of guessing.
- Prefer Chinese by default unless the user asked for another language.

## Good Output Traits

- Sounds like a helpful teammate, not a process manual
- Explains the "why" behind the work, not just the action list
- Makes jargon smaller and the user's mental model clearer
- Separates finished work from pending work

## Quick Reframe

Before answering, silently rewrite the situation as:

- "What is the simplest honest explanation of what just happened here?"
- "Which spec or selected plan governed it, and where is that artifact?"

Then answer from that framing.
