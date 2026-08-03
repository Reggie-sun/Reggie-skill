---
name: important-thing
description: Use when a session uncovers a non-obvious environment fact, active bug, rejected fix, or safety constraint that future agents must remember so they do not repeat the same mistake.
---

# Important Thing

## Overview

This skill is not a handoff formatter.

It is a passive memory rule for costly facts. When work reveals something easy to forget but expensive to rediscover, write it down in a small repo-local memory file so the next agent inherits the lesson instead of replaying the failure.

Default memory file:

- `.agent/context/important-things.md`

Trust code, tests, and live runtime evidence over stale notes. The file exists to preserve hard-won context, not to replace repo truth.

## When To Use

Use this skill when any of these becomes true:

- you discover the real runtime environment differs from the assumed one
- a bug has a misleading symptom or a false lead worth not repeating
- a command must be run in a specific interpreter, container, port, or data path
- a dashboard, metric, or config value is easy to misread
- a safety constraint matters, especially around money, secrets, or destructive actions
- the next window would likely waste time or create risk without this fact

Do not use it for generic summaries, broad plans, or obvious facts already enforced elsewhere.

## Core Rule

If forgetting a fact would cause the next agent to:

- rerun the wrong environment
- chase the same dead end
- trust the wrong metric
- repeat a risky action

then that fact belongs in `important-things.md`.

## What To Record

Record only high-value facts:

- **Environment**: host vs Docker, interpreter path, active server URL/port, DB path, feature flags
- **Live Bug / Gate**: the exact failing symptom or runtime blocker
- **Rejected Paths**: fixes tried and ruled out, especially misleading ones
- **Misleading Signals**: display-only numbers, stale caches, local-vs-remote drift
- **Safety Constraints**: secrets handling, money limits, dirty worktree warnings

Never store secrets. Reference the file or source of truth, not the secret value.

## Write Format

Use this structure:

```text
Updated: <ISO timestamp>

## Active Facts
- Environment: <fact>
- Bug/Gate: <fact or none>
- Don't Repeat: <dead end / misleading assumption / none>
- Safety: <constraint or none>
- Next Check: <one executable verification step>

## Recent History
### <YYYY-MM-DD>
- Learned: <fact>
- Why it matters: <one line>
```

Guidelines:

- Keep `Active Facts` to 3-6 bullets total
- Keep `Recent History` to the 5 most recent entries
- Prefer one-line facts over narrative
- Update facts when reality changes; do not accumulate stale warnings forever

## Read Workflow

When starting meaningful repo work:

1. Read `AGENTS.md`
2. If `.agent/context/important-things.md` exists, read it before planning
3. Carry those facts into your first execution decisions
4. Verify any runtime-sensitive fact against live evidence before acting

If the file conflicts with repo evidence, the file is stale. Fix it after verification.

## Write Workflow

Update `.agent/context/important-things.md` only when the session produced a fact worth preserving.

Good triggers:

- `The app is running in host Python, not Docker`
- `The stop button looked broken because backend thread slept uninterruptibly`
- `Displayed limit is hardcoded UI text; real risk limit lives in config`
- `Local available_balance is bot state, not real-time wallet sync`

Bad triggers:

- `Worked on config`
- `Need more testing`
- `Maybe cookies are bad`

## Relationship To Handoff

This skill is intentionally separate from prompt-generation workflows.

- `important-thing` stores durable mistake-prevention facts
- handoff or prompt skills may quote those facts later
- do not turn `important-things.md` into a session transcript

## Bottom Line

When a fact is costly to forget, promote it into `important-things.md` so the next agent inherits the lesson instead of the mistake.
