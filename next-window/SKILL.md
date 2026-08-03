---
name: next-window
description: Use when the user asks a new window to continue, resume, pick up, hand off, or carry forward an unfinished task or active implementation plan from a previous window.
---

# Next Window

## Overview

This skill is a continuation-prompt generator for a new window.

Its job is to preserve the original active plan as the continuity spine, identify the next executable seam, then package both into a high-signal prompt that the next window can execute with minimal re-orientation.

**Core principle:** `Next One Thing` is the next window's starting seam, not a replacement for the active plan and not an automatic stopping point.

Use it to turn:

- `开新窗口继续`
- `承接上个窗口`
- `从上个窗口接着做`
- `resume the previous task`
- `pick up where we left off`

into a bounded next-window prompt, not passive summarization and not current-window implementation work. The prompt stays inside the approved plan boundary while allowing the next window to continue beyond its starting seam.

## What This Skill Does

1. Find the highest-priority local repo rules
2. Recover the original active plan or, if none exists, the active workflow state
3. Recover one executable `Next One Thing` as the next window's starting seam
4. Reconfirm boundaries from repo evidence
5. Produce one prompt that starts at that seam and continues the remaining approved plan
6. Stop the current prompt-generation turn after delivering the prompt

## Passive Trigger

This skill should trigger passively when the user clearly wants the new window to continue the previous window's work, even if the skill name is never mentioned.

Typical trigger language:

- 继续上个窗口
- 承接上一轮
- 接着上次的任务做
- 按上个窗口继续推进
- 帮我把上一窗口的事情继续做完
- continue from the last window
- resume the prior task

Do not use this skill for brand-new feature ideation, docs-only writing, or standalone reviews that are not about continuing the last execution thread.

## Priority Order

When inside a repository, prefer this order:

1. top-level repo contract such as `AGENTS.md`
2. active plan / workflow artifacts
3. repo-local handoff skill or handoff file
4. code, tests, and current git state
5. older conversational assumptions

If the repo has a local continuation skill such as `window-handoff`, use it as an auxiliary skill. This global skill prepares the next-window prompt; it is not the repo's rule source and it is not the current-window execution driver.

## Start A New Window

### 1. Detect Continuation Intent

Before doing broad exploration, decide whether the user is asking to:

- prepare a bounded next-window prompt
- recover context only
- re-plan because the old task is stale

Default to `prepare a bounded next-window prompt` unless the user explicitly asks for planning only or the repo evidence shows the old next step is no longer valid.

### 2. Read Only The Minimum Correct Context

Read the smallest useful set:

- repo contract and high-priority rules
- active workflow or plan file if one exists
- active handoff file if one exists
- directly relevant files named by the handoff or plan

Do not restart the whole exploration just because a new window will open.

If an active plan exists, read its global constraints, objective, current position, and remaining sequence. Do not read only the local step named by the handoff.

### 3. Reconstruct The Execution Frame

Before writing the prompt, restate:

- current lane
- active plan path and objective, or explicitly `no active plan`
- current position and remaining approved plan sequence
- last window done
- next one thing as the startup seam
- allowed paths or effective scope
- blocker or `none`

If `Next One Thing` is vague, tighten it into one executable step before writing the prompt.

### 4. Validate The Old Next Step

Ask:

- does repo evidence still support this next step?
- is the blocker still accurate?
- did another change make the old plan stale?
- does the next step still fit inside the declared scope?

If yes, keep it as the starting seam of the next-window prompt while preserving the rest of the active plan.

If no, do the smallest necessary repair:

- tighten the scope
- refresh the next step
- upgrade to plan if risk crossed the repo threshold

Repair the existing plan minimally when possible. Do not silently replace it with a new roadmap.

## Plan Continuity Contract

When an active plan exists, the prompt must carry forward:

- the exact plan path
- the plan objective and unchanged contract
- the verified completion point
- the next executable seam
- the remaining approved sequence after that seam

The next window starts with `Next One Thing`, then continues through the active plan at normal high autonomy. Completing the starting seam does not mean the task, session, or plan is complete.

The next execution window stops only at a natural stopping point: the active plan is actually complete, a real blocker appears, a required approval or high-risk decision is reached, or repository rules require a pause. If the user explicitly requests single-step execution, that narrower instruction controls.

If no active plan exists, use the current workflow state and handoff as the continuity spine and say that no active plan was found. If repo evidence proves the plan is stale or complete, repair or close it truthfully instead of inventing continuation work.

## Prompt Only

When this skill is active:

- do not implement the task in the current window
- do not edit code files just because the next step is known
- do not turn the prompt into a fresh roadmap unless the old task is stale
- do produce a ready-to-paste prompt for the next window

This stop rule applies to the current prompt-generation window only. It does not tell the next execution window to stop after `Next One Thing`.

## Prompt Template

Output one concise prompt that includes:

- the repo or worktree path when relevant
- the lane or task type
- the active plan path, objective, current position, and remaining sequence
- the confirmed `Next One Thing`, labeled as the starting seam
- the effective scope or allowed paths
- the blocker state
- any must-read file such as `AGENTS.md`, `session-handoff.md`, `.branch-runtime.local`, or active plan artifacts
- a direct instruction to start at the seam, then continue the active plan rather than re-explore or stop early

Prefer a prompt shaped like:

```text
继续这个仓库上一窗口未完成的任务。先读 AGENTS.md、active plan <plan path>、.agent/context/session-handoff.md，以及需要时的 .branch-runtime.local。
当前 lane: <lane>。Active plan objective: <objective>。
上一窗口已完成：<last window done>。当前 plan 位置与剩余顺序：<current position and remaining sequence>。
只在这个已批准范围内继续：<scope>。Next One Thing（新窗口启动切口，不是停止边界）: <next one thing>。Blocker: <none|blocker>。
如果 repo 证据没有推翻这个切口，直接从这里执行，不要从头大范围重查；完成该切口后继续按 active plan 的既定顺序推进其余已批准任务。不要因为 Next One Thing 完成就停止、宣布 plan 完成或另建 roadmap；仅在 active plan 实际完成、出现真实 blocker、需要高风险决策或 repo 规则要求暂停时停止。
```

## Hard Rules

- Never treat a handoff note as stronger than code, tests, evals, or active plan artifacts.
- Never let `Next One Thing` replace, truncate, or erase an active plan.
- Never treat completion of the starting seam as completion of the task, session, or plan.
- Never widen scope just because the new window has fresh context budget.
- Never convert a single next step into a new roadmap without a clear reason.
- If the repo says a local skill or command must be used for this lane, follow that repo-local rule.
- Never modify implementation files while using this skill.
- If the user explicitly says `先别动代码` or only asks for a summary, keep the prompt even tighter and do not add execution language that exceeds the request.
- If the handoff conflicts with the repository, trust the repository and refresh the next step from evidence.
- If the old task is blocked by unrelated dirty changes in the same target files, stop and surface the conflict.

## Escalation Rule

Stay in prompt-preparation mode unless one of these is true:

- the old next step is no longer safe
- the task crossed into a higher-risk lane
- the boundary is unclear
- required validation changed materially

When escalation is needed, do it briefly and explicitly. Repair the task contract in the prompt, then stop.

## End The Turn

After preparing the prompt:

- do not code
- do not run opportunistic implementation
- keep the starting seam singular and executable while preserving the remaining active plan
- record blocker changes only if they are real and current and necessary for the prompt

Then end the current prompt-generation turn. The generated prompt must tell the next execution window to continue after the starting seam unless a valid stop condition is reached.

## Good Vs Bad

Bad:

- `I read the handoff. Here is a summary.`
- `Let me just fix it here instead of writing the next-window prompt.`
- `The old task looks related, so I expanded it into a broader cleanup.`
- `Next One Thing is done, so the next window should stop even though the active plan still has approved work.`

Good:

- `I confirmed the active plan and next seam, then produced a prompt that starts there and continues the remaining approved plan until a valid stop condition.`
- `The old next step was stale because another file changed, so I tightened the boundary, refreshed the executable step, and wrote that repaired step into the prompt.`

## Output Shape

When you use this skill, finish with:

- the prompt for the next window
- the active plan that remains authoritative, or `no active plan`
- what continuation target was recovered
- whether the starting seam or plan needed repair
