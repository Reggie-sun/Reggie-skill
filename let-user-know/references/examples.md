# Recap Examples

Use these examples to preserve the whole logical window without double-counting
summaries or turning stale context into current fact.

## Contents

- [Example 1: No Compaction](#example-1-no-compaction)
- [Example 2: Substantial Work Exists Only In Compacted Context](#example-2-substantial-work-exists-only-in-compacted-context)
- [Example 3: Compacted Summary Conflicts With Live Evidence](#example-3-compacted-summary-conflicts-with-live-evidence)
- [Example 4: Short Recap Still Reports Spec And Plan](#example-4-short-recap-still-reports-spec-and-plan)
- [Example 5: Compressed Context Preserves Problem And Resolution](#example-5-compressed-context-preserves-problem-and-resolution)

## Example 1: No Compaction

Available context:

- The user asked to fix one API validation bug.
- The agent changed one validator, added two tests, and ran `12 passed`.
- No blocker remains.

Good recap:

```markdown
### 这窗口刚刚做了什么

- 修复了 API validator 对空白 identifier 的错误放行。
- 增加了空字符串和纯空格两个回归测试。
- focused suite 为 `12 passed`，当前没有 blocker。
```

Why it works:

- It covers the goal, implementation, validation, and current state.
- It does not invent a compaction section when no compaction exists.

## Example 2: Substantial Work Exists Only In Compacted Context

Available context:

- A continuation summary says Tasks 1–4 were implemented and committed.
- The summary records a 67-failure baseline comparison and an independent review.
- Visible post-compaction messages only show `$next-window` and handoff preparation.
- Current state still has three focused-test blockers.

Private coverage inventory:

```text
before compaction:
- Tasks 1–4 implementation
- baseline comparison: 67 failures matched exactly
- independent review found invalid green fixtures

after compaction:
- current Git state checked
- next-window prompt prepared

current state:
- three contract-valid focused tests still fail
- runtime and merge gates have not run
```

Good recap:

```markdown
### 这窗口刚刚做了什么

压缩前的主要进展：

- 完成了 Tasks 1–4 的实现和提交。
- 证明当前与基线的 67 个失败集合完全一致。
- 独立 review 发现原来的全绿结果依赖不合法 fixture，恢复真实输入后留下三个 blocker。

压缩后的工作：

- 核对了当前 HEAD、main 漂移和未跟踪文件。
- 生成了下一窗口的 bounded continuation prompt。

当前仍有三个 focused tests 失败，因此 runtime、四账号 smoke 和 merge 尚未执行。
```

Bad recap:

```markdown
- 读取了 handoff。
- 生成了 next-window prompt。
```

Why the bad recap fails:

- It treats compaction as the start of the window.
- It omits nearly all material implementation, validation, review, and blocker work.

## Example 3: Compacted Summary Conflicts With Live Evidence

Available context:

- The compressed summary says `120 passed` and HEAD is `abc123`.
- A later live run reports `3 failed, 117 passed`.
- `git rev-parse HEAD` now reports `def456`.

Good recap:

```markdown
### 这窗口刚刚做了什么

- 压缩摘要记录的较早状态是 `120 passed`、HEAD `abc123`。
- 后续 live verification 已取代该状态：当前 HEAD 为 `def456`，测试为 `3 failed, 117 passed`。
- 因此本轮不能宣称完成，剩余三个失败仍是 blocker。
```

Why it works:

- It preserves useful history without presenting it as current truth.
- It gives precedence to newer repository and test evidence.
- It reports the contradiction instead of silently choosing the more favorable result.

## Example 4: Short Recap Still Reports Spec And Plan

Available context:

- A compacted summary records a task-specific spec at `.agent/specs/rack-fix.md`.
- The approved `plan_ref` is `docs/superpowers/plans/2026-07-16-rack-fix.md`.
- Later work implemented, tested, reviewed, and committed the fix.
- The user asks for a one-sentence recap without process details.

Good recap:

```markdown
已按 `.agent/specs/rack-fix.md` 和 `docs/superpowers/plans/2026-07-16-rack-fix.md` 完成修复、验证与提交。
```

If no task-specific spec or durable plan exists and the user asks where they
are, say that directly. Do not present a session-only `update_plan`, evidence
file, general lane plan, or an unrelated plan that mentions the task as a
substitute.

## Example 5: Compressed Context Preserves Problem And Resolution

Available context:

- A compressed summary records that deployment verification failed because the
  staging configuration targeted the wrong service.
- The agent corrected that configuration and reran the focused suite: `48 passed`.
- The fix was committed.
- Visible post-compaction messages only say that a handoff prompt was prepared.
- The user asks what happened, where it was blocked, and how it was resolved.

Good recap:

```markdown
### 这窗口刚刚做了什么

- 完成了部署验证配置的修复、focused suite 复跑和提交。
- 压缩后的工作只是在准备 handoff；它不是这窗口的全部工作。

### 遇到的问题与处理

- `问题`：部署验证失败，根因是 staging 配置指向了错误的服务。
- `处理`：修正了该配置后重新运行 focused suite。
- `结果`：`48 passed`，修复已提交；当前没有该问题的剩余 blocker。
```

Why it works:

- It recovers the problem, evidence-backed diagnosis, corrective action, and
  verified result from compressed context.
- It does not misrepresent handoff preparation as the only work or as the fix.
