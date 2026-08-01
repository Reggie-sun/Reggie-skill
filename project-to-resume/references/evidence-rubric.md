# Evidence Rubric

## Implementation Status

| Status | Minimum evidence | Resume treatment |
| --- | --- | --- |
| `VERIFIED_PRODUCTION` | Current production or real-user evidence tied to the active path | May state production use within confidentiality limits |
| `VERIFIED_PILOT` | Pilot, acceptance, internal-use, or sign-off evidence | State pilot/internal acceptance, not production |
| `IMPLEMENTED` | Active implementation plus tests or a demonstrated call path | State implemented engineering result only |
| `SHADOW` | Shadow, sidecar, comparison, or non-decisioning path evidence | Explicitly say shadow/comparison mode |
| `EXPERIMENTAL` | Prototype, experiment, branch, notebook, or limited evaluation | Use “探索 / 验证” and name the experiment |
| `PLANNED` | Plan, design, issue, TODO, stub, or proposed path only | Do not write as delivered work |
| `PAUSED` | Explicitly paused, disabled, retired, or shelved | Keep out unless discussing lessons or migration history |
| `UNKNOWN` | Evidence is absent, stale, ambiguous, or conflicting | Require confirmation or omit |

Deployment files, Dockerfiles, CI configuration, or public-deployment instructions do not alone prove deployment.

## Responsibility

| Responsibility | Minimum evidence | Safe verbs |
| --- | --- | --- |
| `INDIVIDUAL` | Explicit user confirmation or strong repository/organizational evidence of sole ownership | 设计、构建、实现、重构、建立、独立负责 |
| `PRIMARY_OWNER` | Evidence of main ownership with collaboration | 负责、牵头（only if explicit）、设计、落地 |
| `COLLABORATIVE` | Team delivery or personal slice is known | 参与、协同、负责其中、与相关人员共同完成 |
| `UNKNOWN` | Commit activity or files exist but the user's role is unproven | 支持、探索、验证、参与方案设计, or ask for confirmation |

Git commits, blame, and contributor counts can support responsibility but never prove `INDIVIDUAL` by themselves. Do not infer the user's Git identity unless the user confirms it.

## Confidence

| Confidence | Evidence shape |
| --- | --- |
| `HIGH` | Code, active call sites, tests/run evidence, and multiple current sources agree |
| `MEDIUM` | Implementation or documentation exists but runtime/business validation is missing |
| `LOW` | Description, comment, TODO, isolated code, stale evidence, or incomplete signal only |
| `USER_CONFIRMATION_REQUIRED` | Ownership, usage, acceptance, confidentiality, or metric depends on user knowledge |

## Metrics

| Metrics class | Rule |
| --- | --- |
| `VERIFIED` | Cite the exact source, population, time window, unit, and evaluation context |
| `DERIVED` | Record formula, inputs, exclusions, and calculation date; label it derived |
| `UNVERIFIED` | Omit or render `[待确认：具体指标]`; never estimate |

Examples of invalid conversions:

- 120 tests → “质量提升 120%”
- 50 commits → “主导核心研发”
- Dockerfile exists → “生产级部署”
- framework provides caching → “独立实现缓存系统”
- benchmark on synthetic fixtures → “真实用户性能提升”

## Resume Eligibility

Set `resume_eligible`:

- `YES`: claim is atomic, non-sensitive, supported at `MEDIUM` or `HIGH`, wording matches responsibility and status, and every number is `VERIFIED` or transparently `DERIVED`.
- `CONDITIONAL`: the engineering fact is supported but ownership, status, publishability, or a metric needs a visible user confirmation placeholder.
- `NO`: claim is planned, contradicted, confidential, unsupported, inseparable from an unverified metric, or materially overstates responsibility/status.

The copy-ready resume may contain `YES` claims. It may contain `CONDITIONAL` claims only with visible `[待确认：...]` markers. It must never contain `NO` claims.

## Evidence Ledger Fields

Every claim must record:

- `claim_id`
- candidate resume claim
- project fact
- user responsibility
- implementation status
- technical evidence
- business evidence
- file paths and stable lines where available
- key symbols, configuration keys, or test names
- Git commits
- tests or evaluation results
- numeric metrics and metrics class
- confidence
- resume eligibility
- required user confirmation
- confidentiality risk
- recommended wording
- evidence freshness and worktree/commit state
