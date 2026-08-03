---
name: strategic-blindspot-audit
description: Use when the user asks the agent to read available conversation history, project memory, repository records, or personal working patterns and identify a non-obvious high-leverage blind spot that could significantly change the user's decisions, priorities, validation strategy, or work system.
metadata:
  short-description: Find a high-leverage strategic blind spot
---

# Strategic Blindspot Audit

Use this skill to synthesize accessible history and project memory into one high-impact insight the user may not fully see.

## Core Rule

Do not pretend to have access to unavailable history. Always state the actual access boundary first.

Use only evidence that is actually visible or readable:

- current conversation context;
- accessible repository memory such as `session-handoff`, `bug-memory`, specs, plans, eval records, and docs;
- local memory or learning logs that are actually readable;
- prior messages visible in the current thread.

## Workflow

1. Define the access boundary.
   - State what was read.
   - State what could not be accessed.
   - Separate direct evidence from inference.

2. Gather evidence.
   - Prefer durable records over vague memory.
   - Look for repeated bug classes, repeated decisions, repeated blockers, and repeated validation gaps.
   - Check for patterns across product, engineering, eval, operations, and workflow.

3. Identify candidate blind spots.
   - A strong blind spot is non-obvious, repeated, decision-changing, and actionable.
   - Avoid obvious summaries like "you need more tests" unless the deeper structure is named.
   - Prefer one sharp thesis over many mild observations.

4. Stress-test the insight.
   - Would this change priorities?
   - Would this prevent future wasted work?
   - Does the evidence cross more than one incident or subsystem?
   - Is this something the user likely underweights?

5. Recommend concrete changes.
   - Give actions that change the user's operating system, release gate, architecture boundary, validation strategy, or decision process.
   - Avoid generic productivity advice.

## Output Format

Use this structure:

```markdown
## Access Boundary
Briefly list what was and was not accessible.

## Pattern Evidence
List concrete evidence. Use file paths or conversation references when available.

## The Blind Spot
State the single most important blind spot in one sentence.

## Why It Changes Decisions
Explain what this changes about priorities, validation, architecture, product, or workflow.

## What To Do Differently
Give 3-5 concrete actions.

## Confidence And Caveats
State confidence and distinguish evidence from inference.
```

## Quality Bar

The answer should feel like a strategic audit, not a memory summary.

Prefer:

- one strong thesis;
- evidence chains;
- decision implications;
- next actions that alter the system.

Avoid:

- pretending to know private history;
- generic reassurance;
- dumping many unrelated observations;
- overfitting to the most recent bug;
- turning every issue into vague process advice.

