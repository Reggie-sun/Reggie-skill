# MiniMax Explorer Evidence Diagnostics

## Record Metadata

- Session ID: `01a01979-f2da-7c00-80b2-65ee2aea9ade`
- Date: `2026-08-19`
- Rollout: `/home/reggie/.codex/sessions/2026/08/19/rollout-2026-08-19T18-03-37-01a01979-f2da-7c00-80b2-65ee2aea9ade.jsonl`
- Affected path: MiniMax external `explorer` through Claude CLI

原始 rollout 可能包含用户输入和环境信息。排查时只做窄提取，不要复制整份 JSONL，也不要把 credential-bearing command 放入报告。

## Executive Diagnosis

这次问题不是 MiniMax 没有返回内容，也不能仅归因于 reasoning effort。Explorer 在一次较宽的 architecture mapping 中读取了部分 lifecycle 文件，然后确定性声称 `VideoGenerationService` 可以原样复用、无需 schema/layout/CLI change；但同一报告的 concerns 又承认 LOCAL receipt/state semantics 尚未深入验证。

Parent 随后检查未被 explorer 读取的 `_lifecycle_schema.py`、`_state_commit_video.py` 和相关 manifest validators，发现 `submit_once()`、`refresh_once()`、`fetch_once()`、attempt state 与 validator 都依赖 paid-provider state。因此原结论缺少足够 evidence，且 summary 与 concerns 自相矛盾。

根因是 orchestration 没有把“必须读取哪些 owner/schema/validator/recovery 文件”做成 runner-enforced contract。提高模型 effort 可能改善推理，但不能保证覆盖缺失文件，也不能阻止未验证的确定性结论。

## Failure Signature

- `status=success` 或 `agent_status=DONE_WITH_CONCERNS`。
- Summary 使用 `can be reused verbatim`、`no schema change required`、`fully compatible` 等确定性措辞。
- Concerns 同时写着某个 receipt、validator、recovery 或 persistence surface 未深入检查。
- Activity stream 中找不到这些关键文件的成功 `Read` 或 file-scoped `Grep` result。
- Parent 读取遗漏文件后能够直接反驳 summary。

看到这一组合时，不要把 transport success 当作 architecture conclusion 已验证，也不要直接派 writer。

## Current Fix

Broad read-only explorer dispatch 应列出 repeated `--require-evidence-path`，覆盖支撑确定性结论所必需的 concrete files。该参数要求 `--dialogue`、Claude-family transport 和 `read-only` permission。

Runner 只把以下行为计为 evidence：

- 对 exact required regular file 成功完成 `Read`。
- 对 exact required regular file 成功完成 file-scoped `Grep`。

Directory-wide `Grep`、失败的 tool result、报告中只提到文件名都不计数。Required evidence declaration 本身不能是 symlink；成功的 `Read`/`Grep` target 会解析到 cwd 内的 canonical required path 后再计数。若模型给出成功终态但 required evidence 不完整，runner 覆盖结果为：

- `status=error`
- `agent_status=BLOCKED`
- `termination_reason=evidence_incomplete`
- 清除模型 `structured_output` 和 prose `result`
- 写入 runner-owned `summary=Required evidence incomplete`
- 在 `blocker` 中列出 required、observed 和 missing paths

这防止被 gate 拒绝的旧结论继续作为第二个 status source 泄露给 parent。

## Dispatch Pattern

```bash
python3 /home/reggie/.codex/skills/sub-agents/scripts/run_subagent.py \
  --agent explorer \
  --cwd /absolute/repo \
  --dialogue \
  --require-evidence-path path/to/owner.py \
  --require-evidence-path path/to/schema.py \
  --require-evidence-path path/to/validator.py \
  --prompt 'Map the bounded behavior and qualify every unresolved conclusion.'
```

Required paths 是 evidence coverage floor，不是允许模型扩大 scope 的文件清单。Parent 仍应给出精确 question，并直接验证重要结论。

## Protocol Compatibility Note

MiniMax 偶尔会把 schema 中的 JSON `null` 输出成字符串 `"null"`。Runner 将仅此精确等价形式（忽略首尾空白与大小写）规范化为 absent `state_file`；其他 non-empty strings 仍必须解析为 cwd 内现存 regular file。该兼容处理不放宽 path boundary。

## Safe Session Checks

```bash
SESSION=/home/reggie/.codex/sessions/2026/08/19/rollout-2026-08-19T18-03-37-01a01979-f2da-7c00-80b2-65ee2aea9ade.jsonl
test -f "$SESSION"
wc -l "$SESSION"
jq -r '
  select(.type == "response_item" and .payload.type == "custom_tool_call")
  | select((.payload.input // "") | contains("run_subagent.py"))
  | [.timestamp, "run_subagent invocation"]
  | @tsv
' "$SESSION"
rg -n -o 'observed_evidence_paths|evidence_incomplete|DONE_WITH_CONCERNS|PROTOCOL_ERROR|BLOCKED' \
  "$SESSION" | head -80
```

不要从 `event=tool:Read` 单独推断读取成功；必须结合其 tool result。不要把 activity heartbeat 当作 semantic evidence。

## Remaining Boundary

Runner 能强制 concrete file coverage，不能从自然语言中机械证明所有跨文件结论都正确，也不能自动识别 required list 本身遗漏了哪个 domain owner。Parent 负责在 dispatch 前选择 evidence set，并在采用高风险结论前检查 summary、findings 与 concerns 是否一致。Task review、scoped re-review 与 final review 继续使用 native `reviewer`。
