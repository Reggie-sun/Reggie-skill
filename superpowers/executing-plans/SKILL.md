---
name: executing-plans
description: Use when you have a written implementation plan to execute in a separate session with review checkpoints
---

# Executing Plans

## Overview

Load plan, review critically, execute all tasks in the repository-authorized
workspace, and report when complete.

**Announce at start:** "I'm using the executing-plans skill to implement this plan."

**Note:** When structured delegation materially improves isolation, recovery,
or independent review, offer superpowers:subagent-driven-development. The
mere availability of subagents is not a reason to switch workflows.

## The Process

### Step 1: Load and Review Plan
1. Apply the repository/global Git lane policy; a plan or this skill alone is
   not a worktree trigger. Use superpowers:using-git-worktrees only when that
   policy requires isolation.
2. Read plan file
3. Inspect the current branch and `git status`
4. Review critically - identify any questions or concerns about the plan
5. If concerns: Raise them with your human partner before starting
6. If no concerns: Create todos for the plan items and proceed

### Step 2: Execute Tasks

For each task:
1. Mark as in_progress
2. Follow each step exactly (plan has bite-sized steps)
3. Run verifications as specified
4. Mark as completed

### Step 3: Complete Development

After all tasks complete and verified:
- On the repository's primary branch, inspect the final diff and status,
  follow repository commit rules, and report the verified result.
- On a feature branch or in a worktree, announce: "I'm using the finishing-a-development-branch skill to complete this work."
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
- Use the current primary branch when repository/global lane rules allow it;
  isolation is risk-driven, not implied by plan execution
