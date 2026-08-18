---
name: sub-agents
description: Run agent definitions as sub-agents. Use when the user names an agent or sub-agent to run, references an agent definition, or delegates a task to an agent.
allowed-tools: Bash Read
---

# Sub-Agents - External CLI AI Task Delegation

Spawns external CLI AIs (codex, claude, cursor-agent, glm, kimi, minimax, grok, gemini, opencode) as isolated sub-agents with dedicated context.

Workflow: discover available definitions, select one from the user request, execute it, and handle the JSON response.

## Resources

- **[run_subagent.py](scripts/run_subagent.py)** - Main execution script
- **[codex.md](references/codex.md)** - Read before first execution from Codex; covers permissions and timeout

**Script Path**: Invoke `python3 {SKILL_DIR}/scripts/run_subagent.py` using the absolute skill path, where `{SKILL_DIR}` is the directory containing this SKILL.md file. Using the interpreter explicitly remains reliable if an installer fails to preserve the executable bit.

## Interpreting User Requests

Extract parameters from user's natural language request:

| Parameter | Source |
|-----------|--------|
| `--agent` | Agent name from the user request or workflow selection |
| `--prompt` | Task instruction part (excluding agent specification) |
| `--cwd` | Current working directory (absolute path) |
| `--cli` | Backend override explicitly requested by the user; otherwise omit |
| `--timeout` | Idle timeout explicitly requested by the user, converted to milliseconds; otherwise omit so the agent definition or global default applies |
| `--allow-command` | Exact Bash command explicitly authorized for a Claude-family `safe-edit` agent; repeat once per command |
| `--allow-path` | File or directory pattern relative to `--cwd` that a Claude-family `safe-edit` agent may edit; repeat once per ownership path |
| `--dialogue` | Require the bounded task-state protocol for a fresh invocation |
| `--parent-answer-file` | Validated prior-turn answer artifact inside `--cwd`; repeat as needed and use only with `--dialogue` |

**Example**:
"Run code-reviewer on src/"
→ `--agent code-reviewer --prompt "Review src/" --cwd $(pwd)`

## Important: Permission and Timeout

This script executes external CLIs that require elevated permissions.

**Before first execution:**
1. Request elevated permissions via your CLI's tool parameters
2. Set the surrounding tool timeout above the effective agent idle timeout; `writer` may define a longer budget than the global 600000ms default

**For Codex CLI** (most common permission issues): See [references/codex.md](references/codex.md) for exact JSON parameter format.

## Workflow

### Step 1: List Available Agents

**Always list agents first** to discover available definitions:

```bash
python3 {SKILL_DIR}/scripts/run_subagent.py --list
```

Output:
```json
{"agents": [{"name": "code-reviewer", "description": "Reviews code..."}], "agents_dir": "/path/.agents"}
```

When the user provides an agent name, select it if it appears in the result. If
it is absent, report the available definitions and wait for a selection. When
the result is empty, provide the Agent Definition Format below and wait for the
user to add a definition.

When the user leaves the agent selection open:

| Available agents | Action |
|------------------|--------|
| 0 | Report that no definitions are available, provide the Agent Definition Format below, and wait |
| 1 | Select it |
| 2+ | Show names and descriptions, then ask the user to select one |

### Step 2: Execute Agent

```bash
python3 {SKILL_DIR}/scripts/run_subagent.py \
  --agent <name> \
  --prompt "<task>" \
  --cwd <absolute-path>
```

Append `--cli <backend>` when the user specifies a backend. Append
`--timeout <milliseconds>` when the user specifies a timeout.
For a Claude-family `safe-edit` agent, append one `--allow-command <exact command>`
per authorized test or Git command. The runner exposes no Bash tool when this
list is empty, and rejects every Bash command not listed exactly.
Append one `--allow-path <relative path>` per owned file or directory pattern;
at least one is required for `safe-edit`, and edits outside those paths are
denied non-interactively.
For a task that may require parent clarification, append `--dialogue`. If the
agent returns `NEEDS_CONTEXT`, write the answer to a UTF-8 artifact inside
`--cwd` and fresh-dispatch the same task with
`--dialogue --parent-answer-file <relative path>`. The answer artifact is
context only: never add it to `--allow-path`, and never place credentials in it.

### Step 3: Handle Response

Parse JSON output and check the transport `status` field:

```json
{"result": "...", "exit_code": 0, "status": "success", "cli": "claude"}
```

**By status:**

| status | Meaning | Action |
|--------|---------|--------|
| `success` | Task completed | Use `result` directly |
| `partial` | Timeout but has output | Review partial `result`, may need retry |
| `error` | Execution failed | Check `error` and `exit_code`; retry after satisfying the reported requirement |

With `--dialogue`, also require `agent_status`; transport success alone never
means that the task completed:

| agent_status | Action |
|--------------|--------|
| `DONE` | Use the result and verify the claimed work |
| `DONE_WITH_CONCERNS` | Inspect the concerns before proceeding |
| `NEEDS_CONTEXT` | Answer its 1-3 questions in an artifact and fresh-dispatch with the same scope and permissions |
| `BLOCKED` | Assess the blocker; do not repeat the unchanged dispatch |
| `PROTOCOL_ERROR` | Correct the prompt/protocol once; do not infer completion from prose |

Dialogue is bounded turn-taking, not an interactive subprocess. The runner
uses `stdin=DEVNULL` and no session persistence. Parent answer files must be
regular, non-symlink UTF-8 files inside `--cwd`, at most 64 KiB; the runner
records their SHA-256 digest in injected context. A parent answer never grants
commands, editable paths, or broader authority.

For configuration or credential errors, retry after the required external
configuration has changed.

**By exit_code** (when status is `error`):

| exit_code | Meaning | Resolution |
|-----------|---------|------------|
| 0 | Success | - |
| 124 | Timeout | Increase `--timeout` or simplify task |
| 127 | CLI not found | Install required CLI (claude, codex, etc.) |
| 1 | General error | Check `error` field in response |

## Agent Definition Location

| Priority | Source | Path |
|----------|--------|------|
| 1 | Environment variable | `$SUB_AGENTS_DIR` |
| 2 | Default | `{cwd}/.agents/` |

To customize: `export SUB_AGENTS_DIR=/custom/path`

## Agent Definition Format

Place `.md` files in `.agents/` directory:

```markdown
---
run-agent: claude
model: sonnet
permission: safe-edit
---

# Agent Name

Brief description of agent's purpose.

## Task
What this agent does.

## Output Format
How results should be structured.
```

`run-agent` supplies the backend; an explicit `--cli` argument overrides it.

**Frontmatter fields:**

| Field | Values | Description |
|-------|--------|-------------|
| `run-agent` | `codex`, `claude`, `cursor-agent`, `glm`, `kimi`, `minimax`, `grok`, `gemini`, `opencode` | Which CLI executes this agent |
| `model` | Backend-specific model name (optional) | Model passed to the selected CLI; omit to use its configured default |
| `effort` | Backend/model-specific reasoning level or OpenCode variant (optional) | Advanced: forwarded as an opaque value. Confirm support for the selected model before setting; omit to use its default. MiniMax uses Claude CLI's `--effort`; unsupported on `cursor-agent` and `gemini` |
| `timeout` | Positive milliseconds (optional) | Per-agent transport idle timeout used when `--timeout` is omitted; read-only Claude-family runs also stop after 120 seconds without semantic progress, while safe-edit uses this configured timeout as its semantic-stagnation cap |
| `permission` | `read-only`, `safe-edit` (default), `yolo` | `read-only` for investigation, `safe-edit` for workspace edits, or `yolo` to bypass approvals and sandboxing |

For Claude-based transports (`claude`, `glm`, `kimi`, and `minimax`),
`read-only` uses `dontAsk`, disables settings inheritance and session
persistence, and exposes only `Read`, `Glob`, and `Grep`. It does not expose
shell, write, plan-transition, task, network, or MCP tools; an empty strict MCP
configuration prevents inherited MCP servers from reopening that surface.
`safe-edit` uses `dontAsk` and likewise disables inherited settings, sessions,
nested-agent, network, plan-transition, and MCP tools. It exposes `Read`,
`Glob`, `Grep`, `Write`, and `Edit`, but only repeated `--allow-path` rules
approve edits; Bash appears only when at least one exact `--allow-command` is
supplied. The runner also injects the resolved path and command grants into the
agent's system context so a denied unlisted command is not mistaken for Bash
being unavailable. Use repeated flags for explicit ownership, focused tests,
and task-only Git commands the parent has authorized. Do not use `yolo` as a
workaround for a missing path or command grant.

## MiniMax Configuration

The `minimax` backend uses Claude CLI with MiniMax's Anthropic-compatible API.

- Set `MINIMAX_API_KEY`; `CLI_API_KEY` remains a legacy fallback. Environment variables take precedence over saved credentials.
- To persist credentials, store `MINIMAX_API_KEY=<key>` in `~/.config/sub-agents/credentials.env` with mode `600`. Set `SUB_AGENTS_CREDENTIALS_FILE` to override this path.
- The default endpoint is `https://api.minimax.io/anthropic`. Coding Plan keys with the `sk-cp-` prefix automatically use `https://api.minimaxi.com/anthropic`; set `MINIMAX_BASE_URL` only to override endpoint selection explicitly.
- The default model is `MiniMax-M3`. Set `model` in the agent frontmatter or `MINIMAX_MODEL` to override it.
