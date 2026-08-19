# MiniMax Writer Session Diagnostics

## Record Metadata

- Session ID: `01a01854-ba4a-7483-a9ac-0ca4f7ae686f`
- Date: `2026-08-19`
- Rollout: `/home/reggie/.codex/sessions/2026/08/19/rollout-2026-08-19T12-43-21-01a01854-ba4a-7483-a9ac-0ca4f7ae686f.jsonl`
- Affected path: MiniMax external `explorer` and `writer` through Claude CLI
- Purpose: 记录可复用的 failure signatures、修复和排查顺序；不是逐消息复述该 session。

原始 rollout 可能包含用户输入、环境信息和 credential-bearing commands。不要整份复制到 issue、prompt 或日志。只提取完成诊断所需的字段，并在分享前检查 secret。

## Executive Diagnosis

这次低效不是单一的“MiniMax 能力不足”，而是 orchestration contract 与 runner capability 没有对齐：

1. `explorer` 已指出 implementation gate 缺少 sealed workflow/profile，parent 仍然派发 writer，导致模型猜实现。
2. host definition resolution 不稳定：绝对 definition path 被当作 agent name，裸 `writer` 又只在 repo `.agents` 中查找。
3. prompt 要求 writer 检查 Git 和运行测试，但 exact `--allow-command` 没覆盖 writer 实际发出的完整 shell string。
4. writer 会给已授权命令追加 `| head`、`&&` 或更窄 selector；exact-command policy 正确拒绝了这些新命令，但旧 runner/parent 反复等待和 fresh-retry。
5. TDD 只存在于上层期望，没有成为 runner 的结构化 invocation contract；一次 writer 先生成了约 1118 行 source draft，之后才尝试测试。
6. 约 30 秒一次的 polling/heartbeat 被反复转述到 parent context，增加 token 和人工观察成本，却不等于 semantic progress。

结论：MiniMax 适合作为 bounded explorer/writer，但必须先证明 implementation-ready，并把 file ownership、完整 shell plan、TDD command 与 terminal-state handling 结构化。Task review、scoped re-review 和 final review 仍走 native `reviewer`。

## Triggering Sequence

以下是触发本轮优化的关键 sequence；同一个 session 后半段还有其他 AI-VIDEO application calls，不要把它们混入 pre-fix failure count。

| Stage | Observed result | Diagnostic meaning |
|---|---|---|
| Two read-only explorer runs | 返回有用 mapping，其中一轮明确指出 Gate 3 缺少 exact local runtime/workflow/profile | explorer 的 unresolved capability 结论应停止 writer dispatch |
| Writer startup with absolute definition path | `termination_reason=runner_validation`，提示 invalid agent name | runner 当时不接受 explicit definition file |
| Writer startup with `--agent writer` | `termination_reason=runner_validation`，只在 repo `.agents` 查找 | host definition fallback 缺失 |
| Hailuo writer | 修改了 owned files，随后发明带 pipe 的测试命令并被拒 | useful artifacts 与 clean terminal result 必须分开判断 |
| Hailuo fresh retry | 新 grant 仍未形成稳定完成路径 | retry 前没有先判断现有 diff 是否已可验证/接管 |
| H3 writer | 先写 oversized source draft、未创建 test，随后运行未授权 collect/head 命令 | implementation readiness 与 TDD contract 同时缺失 |
| H3 fresh retry | 缩小 source 并补 test，但又发明 `&&`/inspection command 后 `BLOCKED` | exact grant 必须被视为完整 shell plan，不能让 writer自由组合 |

`BLOCKED` 不代表“没有任何工作成果”，也不代表“可以接受成果”。它只说明 task 没有可靠完成。Parent 必须先检查 owned diff 和实际 test evidence，再决定 adopt、fix 或一次 bounded retry。

## Root Cause to Fix Map

| Root cause | Current fix | Commit |
|---|---|---|
| Explicit path 和 host definition 无法稳定解析 | `--agent <definition-file>` 可安全解析；裸 name 在未显式选 directory 时回退到 `~/.agents` | `78a4642` |
| External writer 没有显式 TDD transport contract | 新增 `--tdd`，要求且只允许一个 `--tdd-command`，并要求同字符串 `--allow-command` grant | `1395edc` |
| Writer 在缺少 runtime/profile/fixture 时猜实现 | `SKILL.md` 增加 implementation-readiness gate；unresolved explorer finding 是 stop signal | `d5eaea6` |
| Writer 发明 pipe、`head`、`tail`、`&&` 或新 selector | grant list 被定义为 complete shell plan；argv equivalence 只用于诊断，不扩大授权 | `d5eaea6` |
| Prompt 要求 Git inspection，但没给 grant | writer 默认用 `Read`/`Grep` 自查；仅在 exact Git command 已授权时要求 Git | `d5eaea6` |
| Permission denial 后长时间空转 | 第一个真实 policy grant denial 直接生成 structured `BLOCKED` | `d5eaea6` |
| 普通 OS/API/device permission error 被误判 | classifier 只首拒已知 policy markers 或与 tool name 匹配的 Claude denial | `d5eaea6` |
| Useful partial diff 被无条件 fresh-retry | retry 前必须 inspect/adopt artifacts；只有缺失 deliverable 且授权可修正时才 retry | `d5eaea6` |
| 高频 heartbeat 污染 parent context | heartbeat cadence 调整为约 60 秒；unchanged heartbeat 不重复叙述 | `d5eaea6` |

## Current Dispatch Contract

### Before dispatch

确认以下条件全部成立：

- task 的 contract、runtime identity、profile/fixture 已存在，不要求 writer 猜架构。
- 一个 established local pattern 已被点名。
- repeated `--allow-path` 完整覆盖 owned source/test files，但不扩大到 repo root。
- verification 是一个已知、可直接复制的 exact command。
- 若要求 strict TDD，同时传 `--tdd`、一个 `--tdd-command` 和内容完全相同的 `--allow-command`。
- prompt 不要求任何未授权 Git、pipe、shell composition 或 nested agent 行为。

若任一项不成立，留在 parent/explorer lane；不要用 writer 发现 implementation contract。

### While attached

- 以约 60 秒 cadence 观察 activity；unchanged heartbeat 不写入 parent narrative。
- `running` 只表示 process 尚在，不证明健康或 semantic progress。
- 不向 fresh process 写 stdin；`--dialogue` 是 artifact-backed fresh turn，不是 persistent session。
- 不因为一次 poll timeout 就重复 dispatch。

### At terminal state

依次检查三个层次：

1. runner transport：`status`、`transport_exit_code`、`termination_reason`。
2. child CLI：`cli_exit_code`。
3. dialogue task：`agent_status`。

只有 transport success 不能证明 task 完成。`DONE` 仍需 parent 检查 diff 和 tests；`DONE_WITH_CONCERNS` 必须处理 concerns；`BLOCKED` 先检查 artifacts；`PROTOCOL_ERROR` 只允许修正协议后做一次 bounded retry。

## Decision Table

| Signature | Next action |
|---|---|
| `termination_reason=runner_validation` | backend 未启动；修 invocation/definition，不把它算作 MiniMax task failure |
| Explorer 报 missing sealed workflow/profile/runtime | 停止 writer；先补 contract 或维持 design/exploration |
| First policy permission denial | 对比 attempted command 与 exact grants；不要原样继续等待 |
| Generic OS/API/device permission error | 按普通 tool/runtime error 排查；不要自动归类为 allowlist failure |
| `BLOCKED` 且 owned diff 有价值 | parent 独立 review、运行 focused verification；可接管时不 fresh-retry |
| `BLOCKED` 且缺失 deliverable 可由一个明确 grant 修复 | 修正 grant 后最多一次 bounded fresh retry，scope/paths 不变 |
| Owned diff 在 parent verification 中暴露 implementation defect | 这不是 grant retry；由 parent scoped-fix，或重写 bounded brief 后作为新的 writer task 派发 |
| Writer 想运行未列出的 Git/pipe/composite command | 不自动放宽；删除 prompt 要求或显式决定是否授权 exact command |
| `DONE` 但无可信 RED/GREEN evidence | 不接受 strict TDD claim；parent 重新验证并记录证据缺口 |
| Repeated heartbeat without new tool/result | 做 health assessment；不要称为 healthy progress |

## Safe Evidence Queries

先确认 session file，再做窄提取。不要直接 `cat` 整份 JSONL。

```bash
SESSION=/home/reggie/.codex/sessions/2026/08/19/rollout-2026-08-19T12-43-21-01a01854-ba4a-7483-a9ac-0ca4f7ae686f.jsonl
test -f "$SESSION"
wc -l "$SESSION"
```

列出 `run_subagent.py` invocation 的时间和截断后的 command prefix：

```bash
jq -r '
  select(.type == "response_item" and .payload.type == "custom_tool_call")
  | select((.payload.input // "") | contains("run_subagent.py"))
  | [.timestamp, ((.payload.input // "") | gsub("[\\n\\r\\t]+"; " ") | .[0:240])]
  | @tsv
' "$SESSION"
```

统计 attached-process polling，先按 `session_id` 聚合，再结合相邻 start/terminal output 判断属于哪个 external invocation：

```bash
jq -r '
  select(.type == "response_item" and .payload.type == "custom_tool_call")
  | .payload.input // ""
' "$SESSION" \
  | rg -o 'write_stdin\\(\\{session_id: [0-9]+' \
  | sort | uniq -c
```

查 transport/dialogue failure markers 时限制输出长度，并人工检查上下文：

```bash
rg -n 'runner_validation|agent_status|PROTOCOL_ERROR|BLOCKED|DONE_WITH_CONCERNS' \
  "$SESSION" | head -80
```

## Verification Record

本轮 runtime 修复的 latest local gate：

- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s sub-agents/tests -p 'test_*.py'`: `100 passed`。
- `ruff check`、`py_compile` 和 `git diff --check`: passed。
- Native reviewer 最终 verdict: `accept`。

这些是 fake/local regression tests。优化本身没有把 paid MiniMax call 当作 deployment test；同一 AI-VIDEO session 后续的 provider calls 属于 application work，不能替代 runner regression suite。

从本记录写入 skill 起，maintenance deployment gate 已调整：每次修改
`sub-agents` runtime、definition、prompt 或 reference 后，local checks 之外还必须
运行一次与改动匹配的真实付费 MiniMax smoke，并记录三层 terminal status、实际读取或
修改的 files 与 concerns。Documentation-only change 使用 read-only
retrieval/application scenario；runner/writer behavior change 使用 bounded fixture，
不能拿 unrelated project call 代替。

## Remaining Risks

- Runner 注入 strict TDD contract，但不会从 provider event stream 机械重建 RED-before-GREEN；parent 必须检查 report、diff 和 command evidence。
- 若某个已授权命令自己的输出精确伪造 `Permission to use <matching tool> ... has been denied`，classifier 理论上可能 false-positive；这是已接受的窄边缘风险。
- MiniMax invocation 仍然 fresh/stateless。`--parent-answer-file` 只提供经过校验的 context，不提供 live dialogue 或新权限。
- 本次优化降低了无效等待和 retry 条件，但不保证每种 repo/task 都获得相同 wall-clock improvement。

## Escalation Boundary

完成上面检查后仍失败时，报告：exact invocation、resolved definition、owned paths、exact grants、三层 terminal status、是否存在 useful diff，以及已运行的 parent verification。不要粘贴 credential、完整 environment 或未脱敏 rollout。

只有 runner/backend terminal failure、higher-authority conflict 或 external definition 缺少任务必要 capability 时，才 fallback 到 native explorer/writer。Task review、scoped re-review 和 final review 始终使用 native `reviewer`，不是 MiniMax failure fallback。
