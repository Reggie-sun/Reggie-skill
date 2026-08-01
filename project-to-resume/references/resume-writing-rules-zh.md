# Resume Writing Rules - Chinese

## Default Shape

Use an English project title or capability label where it improves recognition, followed by concise Chinese content. Keep technical terms such as `AI Native`, `Harness`, `Agent Runtime`, `RAG`, `Reranker`, and framework/API names accurate.

Build each bullet as:

`动作或职责 + 关键对象 + 技术方案或难点 + 可验证结果`

If business impact is not verified, end with an engineering result such as a passed contract, reproducible output, validated failure gate, deterministic artifact, or covered behavior.

## Responsibility Verbs

- `INDIVIDUAL`: 设计、构建、实现、重构、建立、独立负责
- `PRIMARY_OWNER`: 负责、设计、构建、落地；“牵头” requires explicit evidence
- `COLLABORATIVE`: 参与、协同、负责其中、与相关人员共同完成
- `UNKNOWN`: 支持、探索、验证、参与方案设计，或使用 `[待确认：个人负责范围]`

Only use 主导、从零搭建、独立完成、核心负责人、生产级、企业级 when the ledger supports the exact word.

## Content Priorities

Separate rather than blur:

- architecture design
- feature implementation
- engineering governance and quality gates
- evaluation and benchmark work
- deployment and operations
- business or user results

Avoid repeated technology lists. Mention technology where it explains the solution or difficulty, then keep a compact `技术栈` line.

## Forbidden Inflation

- Do not translate framework defaults into bespoke engineering work.
- Do not translate a plan into a result.
- Do not translate repository scale into business value.
- Do not translate a test pass into production adoption.
- Do not translate team output into personal ownership.
- Do not insert “赋能 / 抓手 / 降本增效 / 显著提升” without specific evidence.
- Do not hide missing facts in vague adjectives.

## Version Consistency

The 2-, 4-, and 6-bullet versions and role-oriented variants must draw from the same eligible claim set. They may change order, compression, and terminology emphasis. They may not change ownership, deployment status, scope, metrics, or confidence.

## Copy-Ready Plain Text

Use exactly this outer shape:

```text
项目名称｜角色
项目简介：……
• ……
• ……
• ……
• ……
技术栈：……
```

Do not put Markdown headings, claim IDs, citations, evidence notes, or reviewer comments in the `.txt` copy. Keep traceability in `resume-project-zh.md` and `evidence-ledger.md`.
