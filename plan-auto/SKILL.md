---
name: plan-auto
description: Use when context indicates Codex should keep going from the latest relevant work with a high-autonomy default, especially after a just-completed task, a partially executed plan, an exposed follow-up fix, or an obvious adjacent implementation step, and Codex should infer the next relevant work from the real local state, verify its own work, correct course when execution drift is found, and keep pushing until a real high-risk blocker appears.
metadata:
  short-description: Continue related work and self-correct as needed
---

# Plan Auto

## Overview

This skill is not a strict plan runner. It is a context-driven continuation skill.

Use it when the work should keep moving forward from the current local context, even if the remaining steps are only partially written down.

Default stance: continue the most relevant next work with high autonomy, validate whether the continuation is still correct, self-correct when reality disagrees with the earlier plan, and keep advancing without waiting for routine confirmation.

## Routing Principle

This skill should not be hard-bound to any particular other skill.

The agent should choose `plan-auto` because the context suggests continuation, not because a specific named skill failed to cover the case.

Context signals are stronger than keyword matching alone.

## When To Use

Use this skill when:

- The user says "继续", "继续往下做", "自动推进", "按刚才的方向继续", "把相关后续也顺手做掉", or equivalent, and recent context gives a clear continuation path
- The current branch, diff, recent test failures, or just-finished task clearly suggest the next adjacent work
- A session plan, checklist, or TODO exists but no longer fully captures the remaining execution details
- The best next step can be inferred from local evidence with acceptable risk
- The agent can tell from recent work that stopping now would leave an obvious nearby slice unfinished

Do not use this skill when:

- The user wants a fresh plan instead of continued execution
- The task boundary is genuinely ambiguous in a high-risk area
- The next steps would be speculative product decisions rather than execution continuation

## Source Of Truth Priority

Build the continuation from the strongest available signals, in this order:

1. The user's latest instruction
2. The just-completed task and the code or tests it changed
3. Existing workflow artifacts such as `IMPL_PLAN.md`, `TODO_LIST.md`, `plan.json`, and `.task/*.json`
4. Failing or newly exposed verification signals
5. Recent session notes and git diff

Do not blindly obey stale checklists when code, tests, or runtime behavior show a newer truth.

## Context-First Triggering

The agent should prefer triggering this skill from situational understanding, not from one magic phrase.

Strong trigger signals include:

- a user asks to continue and there is a clear active thread of work
- the latest change obviously implies the next nearby completion step
- verification reveals the next fix or cleanup directly
- a partial plan exists, but the real current state is more informative than the written task list
- the recent work formed a coherent slice that is not actually finished yet

Weak trigger signals that should not be enough on their own:

- the word "继续" with no recoverable active context
- an old plan that no longer matches the code or tests
- a vague desire for "more work" when multiple unrelated directions are equally plausible

## Core Behaviors

- Default to high-autonomy execution rather than checkpoint-heavy execution
- Continue from the latest real state, not only from the last written plan state
- Infer adjacent next tasks when they are strongly implied by the completed work
- Make the next reasonable local decision instead of escalating routine ambiguity
- Re-check whether the plan is still valid before each next chunk of execution
- If execution reveals a mistake, patch the mistake and continue
- Prefer local correction over escalation when the issue is understandable and low risk
- Keep user interruption rare, short, and milestone-based

## High-Autonomy Default

By default, this skill should feel like an agent that keeps driving.

- Do not pause just because the next step was not spelled out line by line
- Do not ask for confirmation between closely related follow-up tasks
- Do not treat small uncertainty as a blocker when local evidence makes one path clearly more reasonable
- Prefer finishing the surrounding slice of work, not merely the narrowest literal step
- If the work surfaces a nearby missing piece, close it while context is hot
- Escalate only when the risk of guessing is materially higher than the cost of continuing
- Prefer context reconstruction over asking the user to restate what was already visible in the session

## Self-Correction Loop

For each continuation cycle:

1. Reconstruct current state from code, tests, session artifacts, and recent edits
2. Identify the highest-confidence next related task
3. Execute the task with the smallest reasonable amount of hesitation
4. Verify the result against the intended outcome and surrounding behavior
5. If drift, regression, or mismatch is found, diagnose and repair it
6. Re-evaluate what the next task now is
7. Continue until no high-confidence adjacent work remains, the work clearly exits the current slice, or a hard blocker appears

## What Counts As High-Confidence Next Work

Proceed without asking when one or more of these are true:

- A checklist or session task clearly points to the next unfinished item
- A just-completed code change obviously requires the nearby follow-up to be truly complete
- Verification exposes the next fix directly
- The plan omitted a small but necessary closing step such as wiring, tests, schema sync, or cleanup
- The codebase context strongly suggests one adjacent next move and the downside of being wrong is low

Ask the user instead of inferring when:

- Multiple very different next directions are equally plausible
- The next step changes product behavior or scope materially
- The cost of a wrong guess is high and local correction would not be cheap

## Relationship To Existing Plans

Existing plans are guidance, not handcuffs.

- Continue unfinished explicit tasks when they still make sense
- Repair or reorder tasks when reality proves the original sequence wrong
- Add narrowly implied missing steps when needed to finish the surrounding work properly
- Do not silently expand into broad new feature work unrelated to the active slice
- If a named plan and the surrounding code reality diverge, trust the reconstructed current context more than stale wording

## Verification Standard

After each meaningful step or tightly coupled step group:

- Run plan-specified checks when they exist
- Otherwise run the nearest truthful verification
- Check for regressions around the just-touched area
- Do not treat "implemented" as "done" until the result survives verification

## Hard Stop Rules

Stop and ask the user only when:

- A destructive or irreversible action is required
- The next step crosses into materially new scope
- A secret, approval, or unavailable environment is required
- Repeated self-correction is not converging
- The highest-confidence next move is no longer actually high confidence
- There is no single reasonable adjacent path to continue with confidence

## Output Shape

During execution, keep updates short:

- what was completed
- what related step is next
- what was corrected, if anything
- blocker only if autopilot truly had to stop

At the end, report:

- what explicit plan work was completed
- what inferred follow-up work was also completed
- what validations ran
- what corrections were made during execution
- what remains, if anything, and why
