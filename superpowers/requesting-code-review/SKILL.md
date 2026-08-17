---
name: requesting-code-review
description: Use for core behavior, regressions, public contracts, high-risk or semantically subtle changes, and the review gates of an explicitly selected workflow. Review is proportional to semantic risk, not mandatory ceremony for every edit.
---

# Requesting Code Review

Dispatch a code reviewer subagent to catch issues before they cascade. The reviewer gets precisely crafted context for evaluation — never your session's history.

**Core principle:** Review early, review often.

## When to Request Review

**Required when applicable:**
- At the task/final gates of an explicitly selected subagent-driven workflow
- After changing core behavior, safety gates, or public contracts
- For a claimed regression fix or semantically subtle high-risk change

**Optional but valuable:**
- When stuck (fresh perspective)
- Before refactoring (baseline check)
- After fixing complex bug
- Before merging medium-risk work when no existing independent reviewer covers it

Do not create a duplicate ceremony when another independent reviewer already
covers the same responsibility.

## How to Request

**1. Get git SHAs:**
```bash
BASE_SHA=$(git rev-parse HEAD~1)  # or origin/main
HEAD_SHA=$(git rev-parse HEAD)
```

**2. Create the read-only review package:**

```bash
REVIEW_PACKAGE=$(mktemp "${TMPDIR:-/tmp}/superpowers-review.XXXXXX")
{
  git log --oneline "$BASE_SHA..$HEAD_SHA"
  git diff --stat "$BASE_SHA..$HEAD_SHA"
  git diff -U10 "$BASE_SHA..$HEAD_SHA"
} > "$REVIEW_PACKAGE"
```

The controller owns this temporary file. Generate it before dispatch so the
native named `reviewer` profile receives a bounded, reproducible evidence set.

**3. Dispatch code reviewer subagent:**

Dispatch the native named `reviewer` profile, filling the template at
[code-reviewer.md](code-reviewer.md). Do not route this gate through an
external reviewer definition unless a higher-authority user request explicitly
asks for an external provider opinion outside the workflow's review topology.

**Placeholders:**
- `{DESCRIPTION}` - Brief summary of what you built
- `{PLAN_OR_REQUIREMENTS}` - What it should do
- `{BASE_SHA}` - Starting commit
- `{HEAD_SHA}` - Ending commit
- `{DIFF_FILE}` - Absolute path in `$REVIEW_PACKAGE`

**4. Act on feedback:**
- Fix Critical issues immediately
- Fix Important issues before proceeding
- Note Minor issues for later
- Push back if reviewer is wrong (with reasoning)

**5. Remove the exact temporary package after the review is complete:**

```bash
rm -f "$REVIEW_PACKAGE"
```

## Example

```
[Just completed Task 2: Add verification function]

You: Let me request code review before proceeding.

BASE_SHA=$(git log --oneline | grep "Task 1" | head -1 | awk '{print $1}')
HEAD_SHA=$(git rev-parse HEAD)
REVIEW_PACKAGE=/tmp/superpowers-review.example

[Dispatch code reviewer subagent]
  DESCRIPTION: Added verifyIndex() and repairIndex() with 4 issue types
  PLAN_OR_REQUIREMENTS: Task 2 from docs/superpowers/plans/deployment-plan.md
  BASE_SHA: a7981ec
  HEAD_SHA: 3df7661
  DIFF_FILE: /tmp/superpowers-review.example

[Subagent returns]:
  Strengths: Clean architecture, real tests
  Issues:
    Important: Missing progress indicators
    Minor: Magic number (100) for reporting interval
  Assessment: Ready to proceed

You: [Fix progress indicators]
[Continue to Task 3]
```

## Common Rationalizations

| Excuse | Reality |
|--------|---------|
| "I'll just review the diff myself instead of dispatching a reviewer" | You're the coordinator — reviewing the diff inline burns the context window you need to keep driving the work. Dispatch a reviewer subagent: the diff and the evaluation live in its context, and only the findings come back to you. |
| "The reviewer needs my whole session history to understand the change" | Hand it precisely crafted context, never your session's history. That keeps the reviewer on the work product, not your thought process. |

## Red Flags

**Never:**
- Skip review because "it's simple"
- Ignore Critical issues
- Proceed with unfixed Important issues
- Argue with valid technical feedback

**If reviewer wrong:**
- Push back with technical reasoning
- Show code/tests that prove it works
- Request clarification

See template at: [code-reviewer.md](code-reviewer.md)
