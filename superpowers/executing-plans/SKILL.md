---
name: executing-plans
description: Use when you have a written implementation plan to execute in a separate session with review checkpoints
---

# Executing Plans

## Overview

Load plan, review critically, execute all tasks in the current working tree by default, report when complete.

**Announce at start:** "I'm using the executing-plans skill to implement this plan."

**Note:** Tell your human partner that Superpowers works much better with access to subagents. The quality of its work will be significantly higher if run on a platform with subagent support (such as Claude Code or Codex). If subagents are available, use superpowers:subagent-driven-development instead of this skill.

## The Process

### Step 1: Load and Review Plan
1. Read plan file
2. Review critically - identify any questions or concerns about the plan
3. Inspect the current branch and `git status`
4. If concerns: Raise them with your human partner before starting
5. If no concerns: Create TodoWrite and proceed

### Workspace Default

For solo, serial development, default to the current `main` working tree when repository rules allow it. Do not create a feature branch or worktree solely because this skill is being used or because a written plan exists.

Use a worktree only when it solves a concrete isolation need, such as:
- another write-capable agent or session is working concurrently
- unrelated uncommitted changes would overlap or contaminate the plan
- two branches must remain runnable at the same time
- the work is a high-risk experiment
- the repository rules, plan, or human partner explicitly require one

If the current tree contains unrelated changes that make direct execution unsafe, preserve them and use the repository's required isolation path. Never reset or overwrite them.

### Step 2: Execute Tasks

For each task:
1. Mark as in_progress
2. Follow each step exactly (plan has bite-sized steps)
3. Run verifications as specified
4. Mark as completed

### Step 3: Complete Development

After all tasks complete and verified:
- On `main` in a normal working tree: review the final diff and status, follow repository commit rules, and report the verified result. There is no branch to merge or worktree to clean up.
- On a feature branch or in a worktree: announce "I'm using the finishing-a-development-branch skill to complete this work."
- **CONDITIONAL SUB-SKILL:** Use superpowers:finishing-a-development-branch only for feature-branch or worktree completion.

## When to Stop and Ask for Help

**STOP executing immediately when:**
- Hit a blocker (missing dependency, test fails, instruction unclear)
- Plan has critical gaps preventing starting
- You don't understand an instruction
- Verification fails repeatedly

**Ask for clarification rather than guessing.**

## When to Revisit Earlier Steps

**Return to Review (Step 1) when:**
- Partner updates the plan based on your feedback
- Fundamental approach needs rethinking

**Don't force through blockers** - stop and ask.

## Remember
- Review plan critically first
- Follow plan steps exactly
- Don't skip verifications
- Reference skills when plan says to
- Stop when blocked, don't guess
- For solo serial work, use the current `main` working tree by default when repository rules allow
- Isolation is risk-driven, not automatically required by plan execution

## Integration

**Workflow skills:**
- **superpowers:using-git-worktrees** - Use only when the Workspace Default conditions require isolation
- **superpowers:writing-plans** - Creates the plan this skill executes
- **superpowers:finishing-a-development-branch** - Complete development only when execution used a feature branch or worktree
