---
name: discussion-with-claude
description: Use when the user wants Codex to discuss a repository question with Claude, relay the prompt to Claude read-only, and always bring back either Claude's opinion or a clear failure status plus Codex's best-effort judgment.
---

# Discussion with Claude

这是一个轻量 skill。
目标只有一个：把当前讨论问题交给 Claude，然后由 Codex 把 Claude 的结论或失败状态带回当前对话。

核心原则：这个 skill 每次都要响应用户。Claude 可用时带回 Claude 结论；Claude 不可用、超时或输出异常时，明确说明状态，并继续给出 Codex 的 best-effort 判断。

## Use This Skill When

- 用户明确说想“和 Claude 讨论”
- 用户要 `ask claude`、`second opinion from claude`
- 用户希望 Codex 代发问题给 Claude，再整理回传

如果用户要的是 Claude 直接做 code review、challenge、或持续多轮托管会话，不要优先用这个 skill，改用更完整的 `claude` skill。

## What This Skill Does

1. Codex 先把用户当前问题整理成一个简洁 prompt
2. 如果环境里有 `claude` CLI，Codex 用只读方式调用 Claude
3. Codex 读取 helper 的结构化结果
4. 如果 `ok=true`，Codex 提取 Claude 的核心结论
5. 如果 `ok=false`，Codex 报告 Claude 状态，不伪造 Claude 结论
6. Codex 用当前仓库上下文补充判断，再回复用户

## Hard Rules

- 先读 `AGENTS.md`
- 默认只允许 Claude 使用 `Read,Grep,Glob`
- 默认禁止 `Bash,Edit,Write`
- 不把 Claude 当最终裁决者，最终判断仍由 Codex 负责
- 不把 secret、token、密码等敏感信息塞进 prompt
- 不允许因为 Claude 调用失败而沉默；失败也必须回复用户

## Minimal Invocation

优先使用脚本：

```bash
python3 ~/.codex/skills/discussion-with-claude/scripts/relay_to_claude.py --prompt-file "$PROMPT_FILE"
```

脚本默认最多等待 `600s`，给 Claude 足够时间读取上下文并完成较慢的仓库问题讨论。脚本默认无论成功或失败都会向 stdout 输出 JSON，并用 `ok` / `status` / `message` 表达结果；这让 Codex 每次都能继续响应用户。

需要调整 timeout 时：

```bash
python3 ~/.codex/skills/discussion-with-claude/scripts/relay_to_claude.py --prompt-file "$PROMPT_FILE" --timeout-seconds 120
```

如果需要给外部自动化保留失败 exit code，加 `--strict-exit`：

```bash
python3 ~/.codex/skills/discussion-with-claude/scripts/relay_to_claude.py --prompt-file "$PROMPT_FILE" --strict-exit
```

只有 helper 脚本不可用时，才临时直连 Claude：

```bash
timeout 600s claude -p --output-format json --disable-slash-commands --allowedTools Read,Grep,Glob --disallowedTools Bash,Edit,Write < "$PROMPT_FILE"
```

prompt 只需要包含三部分：

- 当前问题
- 最少必要的仓库背景
- 明确要求 Claude 给出结论、风险和建议下一步

## Helper Result Contract

`scripts/relay_to_claude.py` 输出一个 JSON object。调用后先看：

- `ok`: `true` 表示 `result` 可作为 Claude 结论
- `status`: `ok`、`missing_cli`、`timeout`、`command_failed`、`invalid_json`、`empty_result`、`claude_error`、`prompt_missing`、`prompt_error`
- `message`: 给用户看的简短状态
- `result`: 清理过的 Claude 正文；只有 `ok=true` 时才当作 Claude 意见
- `stderr_excerpt` / `stdout_excerpt`: 失败摘要，只在排障时提炼，不整段转发

## Output Contract

如果 `ok=true`，回复用户时默认整理成三段：

- `Claude 认为`
- `我补充判断`
- `建议下一步`

如果 `ok=false`，仍然回复用户，默认整理成三段：

- `Claude 状态`: 用 `status` / `message` 说明没有取得 Claude 结论
- `我补充判断`: Codex 基于当前上下文给 best-effort 判断
- `建议下一步`: 给出可执行下一步；必要时建议稍后重试 Claude

如果 Claude 输出过长，只提炼结论，不整段转发。

## Helper Script

这个 skill 现在带一个很小的辅助脚本：

- `scripts/relay_to_claude.py`

它只做这些事：

- 调 `claude -p`
- 解析 JSON
- 清理 `result` 末尾可能出现的异常标记
- 将成功、缺 CLI、超时、非零退出、非 JSON、空结果统一包装成 JSON

它不负责：

- prompt 生成策略
- 多轮会话编排
- 持久化 session 管理

这样既比手写命令更稳，又不会把 skill 做重。

## Failure Handling

- 没有 `claude` CLI：`status=missing_cli`，明确告诉用户当前环境不能发给 Claude
- Claude 超过脚本 timeout：`status=timeout`，明确告诉用户 Claude 未返回，不要伪造 Claude 结论
- Claude 非零退出：`status=command_failed`，提炼 `stderr_excerpt`
- 返回不是合法 JSON：`status=invalid_json`，报告 Claude 调用失败，并保留关键 stdout / stderr 摘要
- Claude 返回空结果：`status=empty_result`，当作没有取得 Claude 结论处理
- Claude 输出异常标记：先清理再总结，不直接原样倾倒

## Bottom Line

当用户只是想让 Codex 代他“问一句 Claude 并带回意见”时，用这个 skill，保持轻量、只读、可控。无论 Claude 成功还是失败，当前 Codex turn 都要给用户一个明确、诚实、可继续行动的回复。
