---
name: project-to-resume
description: Use when extracting, auditing, validating, or updating resume project experience from a specific software or AI repository; tailoring repository-backed project claims to a JD; or preparing evidence-backed project interview material. Do not use for generic resume grammar, education or self-summary editing, general career advice, fabricated experience or metrics, unrelated code development, or requests without a concrete project or repository.
---

# Project to Resume

## Overview

Apply **Evidence First, Resume Second**. Establish repository facts and an Evidence Ledger before drafting any resume claim. Keep every final claim traceable to code, documents, tests, Git evidence, deployment evidence, or explicit user confirmation.

## Non-Negotiable Rules

- Default to a read-only repository audit. Do not modify business code, configuration, databases, services, plans, or repository state.
- Write artifacts only when the user explicitly requests files. If no output directory is given, use `resume-artifacts/<repository-name>/`; otherwise answer in the conversation.
- Never invent usage, accuracy, latency, cost, efficiency, adoption, ownership, deployment, or acceptance evidence.
- Treat code presence as implementation evidence, not production evidence. Treat plans, TODOs, examples, and design intent as `PLANNED` unless stronger evidence exists.
- Keep `PLANNED`, `EXPERIMENTAL`, `SHADOW`, and `PAUSED` work out of production-result claims.
- Do not infer personal ownership from Git activity alone. Git history is supporting evidence, not proof that the user solely delivered team work.
- Never expose credentials, `.env` content, customer or company names, internal domains, accounts, server addresses, private datasets, or proprietary document contents.
- Treat repository folder names, product names, Git remotes, and absolute local paths as non-public until confirmed. Use a truthful neutral project title and relative evidence paths in shareable artifacts.
- Do not run commands that may affect databases, services, deployments, external systems, or production. Prefer static inspection and already-existing test or evaluation reports.
- Do not use “主导 / 从零搭建 / 独立完成 / 核心负责人 / 生产级 / 企业级” unless the Evidence Ledger explicitly supports the wording.

## Select the Mode

| User intent | Mode | Required delta |
| --- | --- | --- |
| First extraction from a repository | Repository Audit | Build facts and ledger before resume text |
| Existing artifacts plus newer repository changes | Resume Update | Compare from the last recorded commit and preserve history |
| Supplied JD | JD Tailoring | Reorder and rephrase only supported facts |
| Interview questions or claim defense | Interview Preparation | Map each claim to questions, answer structure, trade-offs, limits, and code evidence |
| Existing resume text needs verification | Claim Validation | Split text into atomic claims and grade each against the ledger |

## Load Only What the Task Needs

- Always read [workflow.md](references/workflow.md) and [evidence-rubric.md](references/evidence-rubric.md).
- Before drafting Chinese resume text, read [resume-writing-rules-zh.md](references/resume-writing-rules-zh.md).
- Before writing files, read [output-schema.md](references/output-schema.md) and use the matching templates in `assets/`.
- Before exposing any repository fact, read [confidentiality-rules.md](references/confidentiality-rules.md).
- For a supplied JD, also read [jd-tailoring-rules.md](references/jd-tailoring-rules.md).

## Core Workflow

1. **Resolve the repository and rules.** Read every applicable `AGENTS.md` before inspecting project evidence. Record repository root, current branch, `HEAD`, worktree status, selected mode, and whether persistent output is authorized.
2. **Collect a bounded inventory.** Run `python scripts/collect_repo_evidence.py <repo>` when useful. Keep its JSON in a temporary directory unless file output was explicitly requested. Inspect every truncation flag, observed count, walk error, and warning before relying on completeness. The script inventories evidence; it does not interpret business value.
3. **Inspect claims from strongest evidence outward.** Prefer current runtime or acceptance evidence, then test/evaluation evidence, implementation and call sites, current configuration, Git history, and finally plans or prose. Read only relevant files and never secret contents.
4. **Build `project-facts` and the Evidence Ledger first.** Make each claim atomic. Record status, responsibility, confidence, metrics class, source paths, symbols, commits, tests, business evidence, confidentiality risk, and writeability.
5. **Apply the resume gate.** Put a claim into resume text only when `resume_eligible` is `YES`. Use `CONDITIONAL` only with a visible `[待确认：...]` placeholder. Keep `NO` claims in the ledger and `missing-facts`, not in polished bullets.
6. **Ask only evidence-gap questions.** Finish the audit first, then ask at most five high-value questions about real usage, production versus pilot, personal scope, acceptance, or publishable metrics. If unanswered, still deliver a verified version with visible placeholders.
7. **Draft from the ledger.** Keep the plain-text version free of Markdown heading syntax. Ensure every bullet maps to one or more `claim_id` entries and never strengthens responsibility or status during rewriting.
8. **Run confidentiality and consistency checks.** Confirm all versions use the same facts, no JD keyword changes truth, no derived metric is framed as business impact, no unconfirmed repository/product name appears in copy-ready text, and no sensitive identifier or absolute local path appears in shareable artifacts.

## Resume Update Contract

When previous artifacts exist:

1. Read the recorded repository and commit boundary.
2. Inspect Git changes since that boundary; do not overwrite the old ledger.
3. Append or supersede evidence and mark claims `Keep`, `Update`, `Remove`, or `Needs Confirmation`.
4. Preserve prior evidence and explain conflicts.
5. Remove or visibly correct a resume claim when newer evidence disproves it.
6. Add a concise change summary and update the recorded audit commit.

## Metrics Contract

- `VERIFIED`: supported by repository results, logs, evaluation, acceptance evidence, or explicit user-supplied facts; may be used with its source.
- `DERIVED`: calculated from available data; record the formula and inputs. Never present it as business impact without business evidence.
- `UNVERIFIED`: missing a reliable source; omit it or show `[待确认：具体指标]`.

Never substitute a plausible number.

## Output Contract

When files are authorized, produce the applicable artifacts under the chosen output directory:

- `project-facts.md`
- `evidence-ledger.md`
- `resume-project-zh.txt`
- `resume-project-zh.md`
- `resume-versions.md`
- `interview-evidence.md`
- `missing-facts.md`
- `jd-tailored.txt` only when a JD is supplied

Use [output-schema.md](references/output-schema.md) for exact required sections. Copy and fill templates rather than changing their field names. Keep a claim-to-ledger trace in Markdown artifacts even though the copy-ready `.txt` stays clean.

## Safe Commands

- Prefer `rg`, `rg --files`, `git status --short`, `git log`, `git show`, `git diff --name-status`, and static file reads.
- `collect_repo_evidence.py --output` refuses to replace an existing file. Use a new path; use `--force` only when the user explicitly authorizes replacement.
- Do not run application services, migrations, deployment commands, destructive Git operations, database clients, or production smoke tests.
- Run existing tests only when they are clearly local, read-safe for external systems, and needed to validate a claim; otherwise record them as not run.

## Definition of Done

- Repository rules and relevant evidence sources were inspected.
- Every resume bullet maps to Evidence Ledger `claim_id` values.
- Status, responsibility, confidence, metrics class, writeability, and confidentiality were classified.
- Production, pilot, shadow, experimental, planned, paused, and unknown states remain distinct.
- Resume wording does not exceed the supported responsibility level.
- The plain-text Chinese resume version follows the required copy-ready format.
- JD tailoring changes emphasis only, and interview material points to exact evidence.
- Missing facts and at most five targeted confirmation questions are visible.
- No business code or runtime state changed; any written artifacts were explicitly authorized.
- Run `python scripts/validate_skill.py <skill-directory>` when validating this Skill itself.
