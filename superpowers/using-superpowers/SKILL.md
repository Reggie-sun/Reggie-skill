---
name: using-superpowers
description: Use to route selectively among Superpowers skills or to evaluate whether a high-risk, long-running task should escalate to the full Superpowers workflow. Native Codex remains the default workflow.
---

<SUBAGENT-STOP>
If you were dispatched as a subagent to execute a specific task, ignore this skill.
</SUBAGENT-STOP>

## Default Ownership

Native Codex owns repository exploration, planning, decomposition,
implementation, delegation, review selection, and completion by default.
Skill discovery or platform-mandated invocation is a routing check, not a
lifecycle transfer. If a workflow skill is not selected as primary, it must
not create approval gates, artifacts, or downstream workflow obligations.

## Selective Composition

Classify skills before using them:

- **Workflow skills** such as `brainstorming`, `writing-plans`, and
  `subagent-driven-development` may control lifecycle transitions only after
  explicit selection.
- **Discipline skills** such as `systematic-debugging`, bounded TDD,
  verification, and review may be composed independently around the native
  workflow.
- **Guidance skills** provide domain advice or evidence, then return control
  to the active workflow.

Use the smallest non-overlapping set that materially reduces risk. Read each
selected skill completely, announce it, and obey higher-authority user,
repository, contract, Git-lane, delegation, and verification rules.

## Workflow Escalation

Promote Superpowers to primary workflow only when the full lifecycle clearly
reduces risk: material requirement or architecture ambiguity, multiple
architectural boundaries, a large migration or high rollback cost,
long-session state recovery, several independent implementation units, hard
verification, or an explicit user request.

Do not escalate ordinary documentation, configuration, trivial fixes,
settled bugs, small UI changes, or straightforward single-module features
that native Codex can safely implement and verify in one bounded execution.
Size alone is not a trigger; consider uncertainty, blast radius,
reversibility, verification difficulty, and coordination need.

## Routing Examples

- Settled bug: native inspect/reproduce → fix → proportional verification.
- Ambiguous bug: native workflow + `systematic-debugging`; add regression
  evidence and review when risk warrants.
- Architecture-uncertain feature: `brainstorming` to stabilize contracts,
  then return to native execution or explicitly escalate.
- Large long-running feature: contract/spec → milestone plan → optionally
  select Superpowers/SDD as primary → review → verification.

## Platform Adaptation

If your harness appears here, read its reference file for special instructions:

- Codex: `references/codex-tools.md`
- Pi: `references/pi-tools.md`
- Antigravity: `references/antigravity-tools.md`
- Hermes Agent: `references/hermes-tools.md`

## User Instructions

System/platform requirements, current user instructions, repository rules,
accepted specs/contracts, and global harness policy take precedence over this
skill. A lower-authority skill never expands its own authority.
