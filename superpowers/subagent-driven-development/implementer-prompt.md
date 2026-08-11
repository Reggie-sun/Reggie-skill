# Implementer Subagent Prompt Template

When host policy selects the installed `sub-agents` runner, use this template with the project `writer` definition when present; otherwise use the host-global `writer` definition (`/home/reggie/.agents` on this installation). Do not override its configured MiniMax backend or model by default. If the external runner is unavailable, translate the same role, scope, authority, boundaries, and output contract to the harness's native writer dispatch.

Do not override the writer's configured transport idle timeout or the runner's
semantic-stagnation deadline with a shorter wall timeout. A heartbeat proves
the process is alive but does not prove semantic progress. Stay attached until
the runner returns; Claude-family runs return exit `124` after 120 seconds
without new text or a distinct tool event. Repeated identical heartbeat or
`tool_result` labels must neither trigger an earlier manual interruption nor be
reported as progress. A timeout returns partial text, session id, and last
event for a context-preserving retry decision.

Each invocation is fresh and stateless. For a fix, include the entire original task plus the current state and all review findings again.

```text
Agent: writer
Working directory: [ABSOLUTE_DIRECTORY]

Role: Bounded implementation writer for Task N: [TASK_NAME]

## Task

[FULL TASK TEXT — paste it here; do not make the writer read the plan]

## Context

[Where this task fits, dependencies, relevant architecture, accepted decisions]

## Scope and Authority

- Write-capable only within: [EXACT FILES OR DIRECTORIES]
- Required behavior to preserve: [UNCHANGED CONTRACT]
- Old path to replace/remove, if any: [OLD PATH]
- Do not modify: [EXPLICIT BOUNDARIES]
- Do not stage, commit, reset, clean, revert, or overwrite unrelated changes.
- Assume other agents may be working concurrently; adapt to current files without reverting their work.
- Do not spawn, request, or coordinate subagents.
- If any higher-priority rule conflicts with this scope or authority, stop and report the conflict.

## Current Workspace State

[BRANCH, BASE SHA, RELEVANT git status, FILES ALREADY CHANGED]

## Prior Attempt and Review Findings

[For first attempt: None]
[For a fix: PRIOR WRITER REPORT + EXACT SPEC/QUALITY FINDINGS]

## Execution

1. Inspect repository rules and only the code needed for this bounded task.
2. For behavior changes, follow RED-GREEN-REFACTOR unless TDD is genuinely inapplicable; state why if skipped.
3. Implement exactly the requested behavior with the minimum scoped change.
4. Run: [FOCUSED VERIFICATION COMMAND]
5. Self-review completeness, scope, quality, concurrency safety, and the actual diff.

This runner is non-interactive. If information is missing, do not guess and do not partially improvise. Return `NEEDS_CONTEXT` with the exact missing information. Return `BLOCKED` for an authority, repository-rule, or technical blocker.

## Output

- Status: `DONE`, `DONE_WITH_CONCERNS`, `NEEDS_CONTEXT`, or `BLOCKED`
- Concise implementation summary
- Exact files changed
- Verification commands and results, or why verification was impossible
- Self-review findings
- Risks, concerns, and recommended next step
```
