---
name: subagent-driven-development
description: Use when executing implementation plans with independent tasks in the current session
---

# Subagent-Driven Development

Execute a plan by dispatching a fresh implementation subagent per task, followed by two independent review gates: specification compliance first, then code quality.

**Core principle:** Fresh writer per task + fresh reviewers + parent-owned integration = focused execution without surrendering control.

**Continuous execution:** Do not pause between tasks merely to ask your human partner whether to continue. Stop only for a blocker you cannot safely resolve, material ambiguity, a high-risk decision, scope expansion, or completion.

## When to Use

Use this workflow when:

- A written implementation plan already exists.
- Tasks are sufficiently independent to execute serially with bounded ownership.
- The user wants the work completed in the current parent session.
- Delegation materially reduces context load, implementation risk, or review uncertainty.

Keep tightly coupled work in the parent thread. Use `superpowers:executing-plans` when the work belongs in a separate session.

## Workspace Decision

Before dispatching any writer, the parent inspects repository rules, live-agent ownership, the current branch, and `git status`.

Choose the least costly safe lane:

- **Current working tree, including `main`:** allowed for solo, serial, low-risk work when repository rules permit and there are no unrelated uncommitted changes.
- **Feature branch in the current tree:** use when history isolation is useful but filesystem isolation is not.
- **Dedicated worktree:** use when another writer/session is active, unrelated dirty work exists, two branches must remain runnable, the task is high risk or long lived, or a higher-priority rule requires it.

Use `superpowers:using-git-worktrees` only when the selected lane actually needs a worktree. A branch or worktree is an isolation mechanism, not a mandatory ceremony.

Before implementation, record:

- Problem boundary and acceptance criteria.
- Exact file/module ownership for the writer.
- Behavior or contract that must remain unchanged.
- Old path to replace or remove, when applicable.
- Focused verification command.

## Dispatch Backend and Roles

Follow the higher-priority host delegation policy. On a host configured to prefer MiniMax, use the installed `sub-agents` skill as the default dispatch backend. Resolve agent definitions from the project `.agents` directory first, then fall back to the host's global agent directory (`/home/reggie/.agents` on this installation).

Default role mapping:

| Work | Agent definition | Authority |
|---|---|---|
| Implementation and review fixes | `writer` | Bounded write access to assigned files |
| Spec compliance review | `reviewer` | Read-only |
| Code quality review | `reviewer` | Read-only |
| Final whole-change review | `reviewer` | Read-only |

The installed definitions own their backend and model. On the configured MiniMax path they use `run-agent: minimax`; do not pass `--cli` or override the configured model unless your human partner or a higher-priority rule explicitly requires it.

Let the selected definition own its idle timeout. The host-global maximum-effort `writer` uses 30 minutes; do not replace it with a hard-coded 10-minute wall timeout. Runner heartbeat/activity is evidence of liveness, and active work must not be declared stuck merely because no final report has arrived.

Before the first dispatch:

1. Use `sub-agents` to list/validate the selected definitions.
2. Confirm the external runner and credentials are available without printing secrets.
3. If project and global definitions share a name, prefer the project definition.

If `sub-agents` or the selected definitions are not installed, use the harness's native `Agent`/`Task` mechanism with equivalent bounded writer and read-only reviewer roles. Also use native dispatch when a higher-priority rule requires it or the task needs a capability the external runner cannot provide. State the fallback and reason; never silently change backends. This keeps the core workflow usable without making the external runner a plugin dependency while honoring MiniMax-first host policy where configured.

External CLI calls are **fresh and stateless**. “Same implementer” means the same implementation lane and role, not the same process. Every fix dispatch must repeat the complete task, working directory, allowed files, current workspace state, prior writer report, and exact reviewer findings.

## The Process

### 1. Load and Prepare

Read the plan once. Extract every task with its full text and relevant context. Create entries in the available task tracker (`update_plan` on Codex, `TodoWrite` on Claude).

Do not make a subagent reconstruct the task by reading the plan. Give it the complete task text directly. It may inspect repository files needed to perform its bounded assignment.

### 2. Implement One Task

Dispatch a fresh `writer` using `./implementer-prompt.md`.

The writer must:

- Stay within explicit file and behavior boundaries.
- Avoid reverting or overwriting concurrent work.
- Use RED-GREEN-REFACTOR for behavior changes unless TDD is genuinely inapplicable.
- Run focused verification and self-review.
- Never spawn subagents.
- Never stage or commit unless the parent explicitly grants that authority.

Handle its status:

- **DONE:** proceed to spec review.
- **DONE_WITH_CONCERNS:** assess concerns before review; resolve correctness or scope concerns first.
- **NEEDS_CONTEXT:** add the missing context and re-dispatch a fresh writer.
- **BLOCKED:** change context, task shape, or plan before retrying; escalate if the plan or authority must change.

Never retry an unchanged prompt after a blocker.

### 3. Spec Compliance Review

Dispatch a fresh read-only `reviewer` using `./spec-reviewer-prompt.md`. The reviewer inspects the actual files and diff rather than trusting the writer report.

If rejected, dispatch a fresh `writer` with:

- The complete original task and boundaries.
- Current workspace state and files already changed.
- The previous writer report.
- Every exact reviewer finding.
- The focused verification command.

Then dispatch a fresh spec reviewer again. Repeat until accepted or genuinely blocked.

### 4. Code Quality Review

Only after spec compliance passes, dispatch a fresh read-only `reviewer` using `./code-quality-reviewer-prompt.md`.

Review the actual task change scope. Because the parent normally has not committed yet, this will usually be a working-tree diff from the recorded base SHA plus any task-specific file list. Do not invent a `HEAD_SHA` that excludes uncommitted work.

If rejected, use the same fresh fix-dispatch pattern and re-run code quality review. If a quality fix changes externally visible requirements, run spec review again before returning to quality review.

### 5. Parent Integration

After both task gates pass, the parent:

1. Inspects `git diff` and confirms every changed line belongs to the task.
2. Runs the focused verification from a known workspace state.
3. Stages only explicit task files.
4. Commits this task's stable checkpoint when repository policy requires or permits it; do not defer several accepted tasks into one commit unless the repository policy or task shape calls for that.
5. Marks the task complete in the task tracker.

The parent owns Git operations, conflict resolution, scope decisions, and the final implementation path. Passing reviews does not transfer that responsibility.

### 6. Final Review and Completion

After all tasks, dispatch one fresh read-only `reviewer` over the complete implementation. The final report must include:

- Verdict: `accept`, `accept with concerns`, or `reject`.
- Blocking issues and non-blocking concerns.
- Evidence from files and verification.
- Recommended minimal follow-up.

The parent verifies important review claims, inspects final status/diff, and runs proportional final checks. If work used a feature branch or worktree, use `superpowers:finishing-a-development-branch`; otherwise complete directly in the current-tree lane and report the result to your human partner.

## Prompt Templates

- `./implementer-prompt.md` — fresh MiniMax writer or fix writer
- `./spec-reviewer-prompt.md` — fresh MiniMax spec reviewer
- `./code-quality-reviewer-prompt.md` — fresh MiniMax quality/final reviewer

## Example Workflow

```text
Parent: Read plan once, extract tasks, inspect Git state, choose clean-main lane.
Parent: Validate project/global writer and reviewer definitions through sub-agents.

Task 1:
  Fresh MiniMax writer -> tests + implementation + self-review, no commit
  Fresh MiniMax reviewer -> spec reject: missing progress reporting
  Fresh MiniMax writer -> receives full task + current state + exact finding; fixes
  Fresh MiniMax reviewer -> spec accept
  Fresh MiniMax reviewer -> quality reject: magic number
  Fresh MiniMax writer -> receives full context; fixes and verifies
  Fresh MiniMax reviewer -> quality accept
  Parent -> reviews diff, verifies, stages exact files, commits checkpoint

After all tasks:
  Fresh MiniMax reviewer -> whole-change verdict
  Parent -> verifies claims and completes the selected Git lane
```

## Red Flags

Never:

- Spawn multiple writers into the same working tree or overlapping files.
- Use a worktree automatically without an actual isolation trigger.
- Modify a dirty current tree when unrelated user work is present.
- Let an external writer stage, commit, reset, clean, or revert by default.
- Assume a fresh external invocation remembers a prior conversation.
- Replace the writer's configured idle timeout with a shorter fixed wall deadline.
- Ask a subagent to infer the task from the plan instead of receiving full task text.
- Skip spec or quality review, reverse their order, or skip re-review after fixes.
- Treat self-review as a substitute for independent review.
- Continue while either review has blocking findings.
- Accept a subagent summary as verified truth.
- Let any subagent spawn or coordinate other subagents.
- Silently fall back from the host's preferred backend to another backend.

## Integration

**Primary dispatch skill:**

- **sub-agents** — When installed and selected by host policy, runs the preferred MiniMax `writer` and `reviewer` definitions. Native `Agent`/`Task` remains the portable fallback.

**Workflow skills:**

- **superpowers:writing-plans** — Produces the plan this skill executes.
- **superpowers:test-driven-development** — Governs behavior-changing implementation.
- **superpowers:requesting-code-review** — Supplies review content and calibration.
- **superpowers:using-git-worktrees** — Conditional, only when workspace isolation is required.
- **superpowers:finishing-a-development-branch** — Conditional, only for branch/worktree completion.

**Alternative:**

- **superpowers:executing-plans** — Use when execution belongs in a separate session.
