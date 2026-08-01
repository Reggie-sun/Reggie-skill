# Output Schema

Create only artifacts applicable to the user request. When writing is authorized and no path is specified, use `resume-artifacts/<repository-name>/`.

Treat `project-facts.md` and `evidence-ledger.md` as evidence-working artifacts, but still avoid secrets and normalize absolute local paths to `<REPOSITORY_ROOT>`. Treat all resume, interview, missing-facts, and JD artifacts as shareable. Use a truthful neutral project title until the repository or product name is confirmed public.

## `project-facts.md`

Required sections:

- `Audit Metadata`: neutral repository label, normalized root, branch, audited commit, worktree state, audit date, mode
- `Project Goal`
- `Application Context`
- `User Responsibility`
- `Architecture`
- `Technology Stack`
- `Core Modules`
- `Engineering Challenges`
- `Implementation Stage`
- `Verification Results`
- `Known Limitations`
- `Evidence Gaps`
- `Change Summary` for Resume Update

Use `assets/project-facts-template.md`.

## `evidence-ledger.md`

Keep one atomic claim block per `claim_id`. Include every field in `references/evidence-rubric.md`. Preserve prior entries during updates; mark superseded evidence rather than deleting it.

Use `assets/evidence-ledger-template.md`.

## `resume-project-zh.txt`

Use `assets/resume-project-template.txt`. It must be directly copyable, contain no Markdown headings, citations, claim IDs, or internal warnings, and use visible placeholders for any conditional fact.

## `resume-project-zh.md`

Include:

- project title and role
- project summary
- 4 standard bullets
- technology stack
- `Evidence Mapping` from each bullet to `claim_id`
- bounded notes or placeholders requiring confirmation

## `resume-versions.md`

Include all five variants:

1. concise: 2 bullets
2. standard: 4 bullets
3. detailed: 6 bullets
4. technical-lead-oriented
5. AI-application-engineer-oriented

Record the `claim_id` set used by each variant. Keep facts, responsibility, status, and numbers consistent.

## `interview-evidence.md`

For every resume claim include:

- likely follow-up questions
- recommended answer structure
- technical evidence and code entry
- design trade-offs
- failure modes and limitations
- what must not be overstated

Use `assets/interview-evidence-template.md`.

## `missing-facts.md`

Required sections:

- Missing Business Metrics
- Missing Responsibility Evidence
- Missing Deployment or Acceptance Evidence
- High-Value Questions, maximum five
- Claim Improvements unlocked by each answer

## `jd-tailored.txt`

Generate only when a JD is supplied. Include:

- JD core capability groups
- supporting project evidence
- keyword coverage
- reordered project content
- tailored copy-ready project version
- capability gaps

Do not hide gaps or convert adjacent skills into direct experience.
