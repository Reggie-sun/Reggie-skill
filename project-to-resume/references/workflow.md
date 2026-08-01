# Workflow

## 1. Establish the Audit Boundary

Record:

- repository root and repository name
- applicable `AGENTS.md` files
- branch, `HEAD`, and dirty worktree summary
- selected mode
- output authorization and output directory
- requested role or JD, if any

Do not treat dirty files as invalid evidence, but label them `WORKTREE_ONLY` and do not imply they are committed, reviewed, deployed, or authored by the user.

## 2. Build the Evidence Map

Inspect selectively, starting with direct evidence for likely project claims:

1. `README`, project documentation, specs, ADRs, RFCs, and API documents
2. dependency manifests and runtime entry points
3. core business code plus callers and consumers
4. tests, fixtures, evaluation reports, benchmarks, and already-produced run evidence
5. schema, migrations, deployment manifests, CI/CD configuration, Docker, Compose, or Kubernetes files
6. Git log, diff, blame, and shortlog
7. issues, PRs, and releases only when already accessible in the current environment

File counts, lines of code, contributor counts, and commit totals indicate scale only. They do not prove business value, technical quality, ownership, or deployment.

Use `scripts/collect_repo_evidence.py` for a bounded inventory. Inspect its `limits`, `warnings`, `walk_errors`, observed counts, and every `*_truncated` field before trusting completeness. A partial inventory is evidence of what was found, never proof that missing evidence does not exist.

## 3. Convert Evidence into Atomic Claims

Split compound statements. “设计并上线高性能 RAG，准确率提升 30%” contains at least four claims:

- designed the RAG architecture
- personally owned the design
- deployed to production
- improved a named metric by 30%

Grade each independently. A bullet is limited by its weakest necessary claim.

For each claim, record exact evidence locations:

- stable `path:line` when available
- otherwise path plus class, function, configuration key, test name, or commit hash
- evidence type and whether it is current, historical, or worktree-only

## 4. Resolve Conflicts

Use this precedence for implementation and runtime truth:

1. current authenticated production or user evidence
2. current pilot acceptance, real runtime replay, or formal evaluation
3. current integration or behavior tests
4. current implementation plus active call sites
5. current configuration and deployment manifests
6. Git history
7. documentation, plans, comments, or TODOs

Higher precedence does not automatically prove personal ownership. Resolve status and responsibility separately.

If sources conflict, classify `UNKNOWN` or `USER_CONFIRMATION_REQUIRED`, explain the conflict, and keep the stronger resume wording out.

## 5. Ask after Auditing

Ask no more than five questions, and only where an answer can promote or repair a specific claim. Prefer:

1. Is the active path in production, a pilot, internal use, shadow mode, or not deployed?
2. Which exact modules or decisions did you personally own?
3. What acceptance or sign-off occurred, and can it be described publicly?
4. Which performance, quality, or efficiency results have a source?
5. What sensitive names or details must be anonymized?

Link every question to affected `claim_id` values.

## 6. Mode-Specific Procedures

### Repository Audit

Create the project facts and ledger before any resume text. Generate only eligible claims.

### Resume Update

Read the prior audit commit from `project-facts.md`. Use `git diff --name-status <old>..HEAD`, relevant commit history, and current evidence. Preserve old claim records and add:

- change type: `Added`, `Modified`, `Invalidated`, or `Conflicted`
- resume action: `Keep`, `Update`, `Remove`, or `Needs Confirmation`
- old and new evidence boundary

### JD Tailoring

Extract the JD capability groups, map them to existing `claim_id` values, then reorder or rephrase. Record gaps separately. Do not add implied capabilities.

### Interview Preparation

For every resume bullet, generate likely follow-ups, a Situation/Problem → Action → Trade-off → Result → Limitation answer frame, exact code evidence, failure modes, and wording that must not be overstated.

### Claim Validation

Atomize the supplied resume text and grade each claim as `Supported`, `Partially Supported`, `Unsupported`, or `Confirmation Required`. Provide the safest corrected wording.

## 7. Final Cross-Check

Verify:

- each bullet cites one or more ledger IDs in the editable Markdown artifact
- all versions agree on status, role, and metrics
- `.txt` contains no Markdown heading markers and no internal evidence notes
- any placeholder is visibly bracketed
- no sensitive values or private identifiers appear
- copy-ready titles use a neutral description until repository/product-name publishability is confirmed
- shareable artifacts use relative paths or `<REPOSITORY_ROOT>`, not absolute home paths
- output writes occurred only with explicit authorization
