---
name: writing-plans
description: Use when the user explicitly requests a durable implementation plan, or when approved work is high-risk, long-running, cross-boundary, or needs non-obvious sequencing, ownership, migration, rollback, or delegated handoff. Do not use for settled bounded changes.
---

# Writing Plans

## Overview

Write contract-oriented implementation plans that preserve the decisions an
executor must not rediscover. Prefer boundaries, invariants, compatibility,
acceptance criteria, verification, and major milestones over a transcript of
every edit or command.

## Routing Gate

Use this skill for an explicitly requested durable plan, or when execution is
high-risk, long-running, cross-boundary, delegated, or has non-obvious
sequencing, ownership, migration, rollback, or verification dependencies. A
written spec and task size alone are not triggers. For settled bounded work,
return control to the active workflow without creating a plan artifact.

**Announce at start:** "I'm using the writing-plans skill to create the implementation plan."

**Context:** If working in an isolated worktree, it should have been created via the `superpowers:using-git-worktrees` skill at execution time.

**Save plans to:** `docs/superpowers/plans/YYYY-MM-DD-<feature-name>.md`
- (User preferences for plan location override this default)

## Scope Check

If the spec covers multiple independent subsystems, it should have been broken into sub-project specs during brainstorming. If it wasn't, suggest breaking this into separate plans — one per subsystem. Each plan should produce working, testable software on its own.

## Output Language Contract

Unless the user or repository says otherwise, use English Markdown headings
and Chinese narrative body text. Keep commands, paths, filenames, symbols,
API/type names, config keys, errors, logs, commit messages, and established
technical terms in their original form.

## File Structure

Before defining tasks, map out which files will be created or modified and what each one is responsible for. This is where decomposition decisions get locked in.

- Design units with clear boundaries and well-defined interfaces. Each file should have one clear responsibility.
- You reason best about code you can hold in context at once, and your edits are more reliable when files are focused. Prefer smaller, focused files over large ones that do too much.
- Files that change together should live together. Split by responsibility, not by technical layer.
- In existing codebases, follow established patterns. If the codebase uses large files, don't unilaterally restructure - but if a file you're modifying has grown unwieldy, including a split in the plan is reasonable.

This structure informs the task decomposition. Each task should produce self-contained changes that make sense independently.

## Task Right-Sizing

A milestone is the smallest implementation unit that has a coherent owner,
contract, and verification seam. Split work where ownership, rollback,
dependency ordering, or independent review materially benefits; do not split
one bounded change into ceremony-sized tasks.

## Detail Level

For normal plans, state the outcome, affected boundaries, constraints, and
verification for each milestone. Do not require by default:

- 2-5 minute microsteps
- complete implementation or test code
- exact line ranges before repository evidence supports them
- a separate plan step for every test run, command, or commit

Add lower-level task briefs only when long-running or delegated execution
needs them for context isolation and independent ownership.

## Plan Document Header

Use the applicable parts of this header; omit sections that do not constrain
the work:

```markdown
# [Feature Name] Implementation Plan

**Goal:** [One sentence describing what this builds]

**Scope:** [What is included]

**Contract Surfaces:** [Public API, CLI, schema, persistence, protocol,
state, artifact, or error boundaries that must remain stable]

**Invariants:** [Properties that must remain true]

**Current / Target Behavior:** [The observable change]

**Compatibility:** [Version, migration, rollback, and consumer constraints]

**Out of Scope:** [Explicit exclusions]

**Acceptance Criteria:** [Observable completion conditions]

**Verification:** [Focused and broad executable evidence]

**Spec / ADR:** [Paths to binding artifacts, when present]

## Major Milestones

---
```

## Task Structure

````markdown
### Milestone N: [Outcome]

**Files:**
- Create: `exact/path/to/file.py`
- Modify: `exact/path/to/existing.py`
- Test: `tests/exact/path/to/test.py`

**Owner / Dependencies:** [Only when coordination requires them]

**Contract:** [What this milestone consumes, produces, or must preserve]

**Implementation Notes:** [Decisions and repository patterns that materially
constrain the implementation; omit code that the executor can derive safely]

**Acceptance:** [Milestone-specific observable result]

**Verification:** [Exact command or runtime check when known]
````

## No Placeholders

Every milestone must contain the decisions an executor cannot safely infer.
These are **plan failures**:
- "TBD", "TODO", "implement later", "fill in details"
- "Add appropriate error handling" / "add validation" / "handle edge cases"
- "Write tests for the above" without naming the behavior or verification seam
- "Similar to Milestone N" when the relevant contract is not restated or linked
- References to contracts, types, or artifacts that are neither defined nor linked

## Self-Review

After writing the complete plan, review it with fresh eyes and check it against
the accepted spec or requirements. This is a checklist you run yourself — not
a subagent dispatch.

**1. Spec coverage:** Skim each section/requirement in the spec. Can you point to a task that implements it? List any gaps.

**2. Placeholder scan:** Search your plan for red flags — any of the patterns from the "No Placeholders" section above. Fix them.

**3. Type consistency:** Do the types, method signatures, and property names you used in later tasks match what you defined in earlier tasks? A function called `clearLayers()` in Task 3 but `clearFullLayers()` in Task 7 is a bug.

If you find issues, fix them inline. No need to re-review — just fix and move on. If you find a spec requirement with no task, add the task.

## Execution Handoff

After saving the plan, return control to the active workflow.

- If the user requested plan-only work, stop after reporting the artifact.
- Use Native Codex for bounded serial execution when it remains the safest
  primary workflow.
- Select `subagent-driven-development` or `executing-plans` only when the
  active Global/Repository policy and the task's risk, duration, state, or
  coordination needs justify that escalation.
- A completed plan is not itself an escalation, delegation, worktree, review,
  or commit trigger.
