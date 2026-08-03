---
name: agent-memory-capture
description: Use automatically when the user asks to preserve session lessons, repeated mistakes, repo-specific pitfalls, notes for the next agent, "don't repeat this" guidance, or says a previously correct behavior was broken by a later change, by deciding the smallest correct destination among repo-local bug-memory, AGENTS.md, a repo-defined continuation target, or nowhere, and writing only that update.
---

# Agent Memory Capture

## Overview

This skill captures reusable lessons without polluting long-lived project memory.

Its job is to make one of four decisions:

1. Route a repo-specific regression lesson into a repo-local bug-memory target, if one exists
2. Write a concise durable rule into `AGENTS.md`
3. Write lightweight execution continuity into a repo-defined continuation target, if one exists
4. Decide the note should not be persisted

## When To Use

Use this skill when the user asks for any of the following:

- 把当前会话的踩坑写给下个 agent
- 把经验沉淀进 `AGENTS.md`
- 记录值得长期保留的项目注意事项
- 整理“不要再犯”的规则
- 判断某条观察应该写进 `AGENTS.md`、repo continuation target，还是根本不该写
- 指出“你把之前的逻辑搞坏了”“修 A 坏 B 了”“又回归了”并希望下个 agent 别再犯

This skill should also trigger passively when the user clearly wants to leave durable notes for future agents, even if they do not mention the skill name.

When the user is specifically saying that a previously correct behavior was broken by a later code change, this skill should trigger first at the global layer, then decide whether the lesson belongs in a repo-local regression memory such as `.agent/bug-memory/` or in some other destination.

Do not use this skill for normal feature work, broad documentation refreshes, or speculative brainstorming.

## Decision Rule

### Write To Repo-Local Bug Memory

Route the lesson to a repo-local bug-memory target when all of the following are true:

- the repository defines a concrete regression-memory target such as `.agent/bug-memory/` or a repo-local `bug-memory` skill
- the user is describing a repeatable regression class, especially "previously good behavior was broken by a later change"
- the lesson can be tied to concrete file paths or change surfaces
- the next agent would benefit from explicit regression checks, not just a prose reminder

Good repo-local bug-memory cases usually include:

- the previously correct behavior
- the now-broken behavior
- the risky file surface
- the regression checks needed next time

Do not force these lessons into `AGENTS.md` when they are really project case records rather than durable repo rules.

### Write To `AGENTS.md`

Only write to `AGENTS.md` when the note is:

- durable across sessions
- project-specific, not generic coding advice
- likely to prevent a repeated mistake or bad diagnosis
- backed by current-session repetition or durable repo evidence
- expressible as one concise rule

Good `AGENTS.md` rules usually include:

- the trigger: when this situation appears
- the required action: what the agent must check or do
- the avoided failure mode: what mistake this prevents

### Write To A Repo Continuation Target

Write to a continuation target only when the repository explicitly defines one and the note is about execution continuity, such as:

- the next concrete step
- blocker status
- branch/runtime coordinates
- the current judgment after code or verification changed

Continuation memory is temporary execution state, not project policy.

### Write Nowhere

Do not persist notes that are:

- speculative
- one-off debugging facts
- pasted logs or command output
- roadmap items or backlog ideas
- generic advice that belongs in the model prompt already
- duplicate of an existing rule
- too long to be a rule

## Workflow

### 1. Read The Right Context

- Read `AGENTS.md` first when it exists.
- If the repository defines a repo-local regression memory layer, read the smallest relevant bug-memory docs before deciding whether the lesson should become a case record instead of an `AGENTS.md` rule.
- If the repository defines an active continuation target such as a handoff file or repo-local continuation skill, read that before deciding whether the note is only temporary.
- Read only the smallest relevant evidence needed to justify the note.

### 2. Draft Up To Three Candidate Notes

For each candidate, classify it as:

- `bug-memory`
- `agents`
- `continuation`
- `discard`

If you cannot justify a note with evidence, classify it as `discard`.

### 3. Apply The Quality Filter

Before writing, check every candidate:

- Is it specific to this repository?
- Will it still be useful in a later session?
- Does it tell the next agent what to do differently?
- Is it shorter than two sentences?
- Does an equivalent rule already exist?

If any answer is no, either tighten the wording or discard it.

For regression complaints such as "you broke the previous logic" or "you fixed A but broke B", also check:

- Can I name the previously correct behavior?
- Can I name the now-broken behavior?
- Can I point to at least one concrete file path?
- Can I describe at least one concrete regression check?

If these answers are yes and the repo has a bug-memory layer, prefer `bug-memory` over `AGENTS.md`.

### 4. Update The Smallest Correct Target

For repo-local bug-memory:

- Prefer routing into the repo-defined regression-memory workflow instead of improvising a global format.
- Keep the record focused on one regression class.
- Preserve concrete `surface` and `regression_check` details whenever the repo-local format supports them.

For `AGENTS.md`:

- Prefer adding one short bullet under an existing relevant section such as hard-earned rules.
- Do not create a new control plane, roadmap, or long lessons section.
- If the rule changes lane classification, risk gates, or file ownership behavior, also verify whether the machine-readable policy source must be updated.

For a continuation target:

- Keep only the current execution judgment.
- Do not copy rationale, plans, or logs into continuation memory.

### 5. Validate

- Re-read the edited section.
- Check for contradiction with higher-priority repo documents.
- Run minimal text validation such as `git diff --check` when working inside a git repo.

## Hard Rules

- Never turn `AGENTS.md` into a changelog, notebook, or postmortem dump.
- Never write a repo-specific regression case into global memory when the repository already has a repo-local bug-memory destination that can carry file paths and regression checks.
- Never promote a temporary workaround into a durable rule without evidence.
- Never add a rule that merely repeats existing instructions with new wording.
- For `AGENTS.md` or repo-defined continuation-target memory-capture writes, do not block on unrelated uncommitted changes; write the minimal intended note directly without trying to clean up, revert, or reformat surrounding edits.
- Prefer one strong rule over several weak observations.

## Good Vs Bad

Bad:

- `Remember to be careful with tests.`
- `This file was annoying.`
- `Maybe the worker is remote.`

Good:

- `命中 ingestion / worker 排查时，先确认活跃 worker 宿主归属，再判断问题属于本地 API 还是远端 worker，避免只看本地 compose 就误判。`
- `当一条经验只影响当前窗口的下一步、blocker 或 runtime 坐标时，只有 repo 明确定义了 continuation target 才写入；否则不要把临时状态升级成 AGENTS 长期规则。`

## Output Shape

When you use this skill, finish with:

- what destination was chosen: `bug-memory / AGENTS / continuation / none`
- what was written
- why that target was chosen
- what was intentionally not persisted
