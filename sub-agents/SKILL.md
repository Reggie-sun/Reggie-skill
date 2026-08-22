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
- **[minimax-writer-session-diagnostics.md](references/minimax-writer-session-diagnostics.md)** - Read when MiniMax dispatch repeatedly blocks, retries without progress, invents shell commands, or produces useful edits without a clean terminal result
- **[minimax-explorer-evidence-diagnostics.md](references/minimax-explorer-evidence-diagnostics.md)** - Read when a MiniMax explorer returns a confident architecture or compatibility conclusion without inspecting every required owner, schema, validator, and recovery surface

**Script Path**: Invoke `python3 {SKILL_DIR}/scripts/run_subagent.py` using the absolute skill path, where `{SKILL_DIR}` is the directory containing this SKILL.md file. Using the interpreter explicitly remains reliable if an installer fails to preserve the executable bit.

## Maintenance Verification

After every change to this skill's runtime, agent definitions, prompts, or
reference documentation, run the relevant local checks and then one real paid
MiniMax invocation before deployment. Match the live smoke to the change: use
a read-only retrieval/application scenario for documentation, and a bounded
fixture with explicit paths and commands for runner or writer behavior. Do not
substitute fake/unit tests for this live gate, expose credentials in the prompt,
or use unrelated project work as proof. Record the terminal transport fields,
`agent_status`, files actually read or changed, and remaining concerns.
The terminal `runner_context` records only the resolved model identifier,
effort, permission profile, `tools_mode`, and exposed tool names. Treat it as runner truth for
configuration diagnostics; it never contains prompts, command grants, provider
prose, environment values, or credentials.

## Automatic MiniMax Problem Capture

The main-thread agent MUST invoke `capture-minimax-session` after a MiniMax
dispatch reaches a stable terminal or stopping point and exposes a probable
runner, transport, permission, protocol, evidence-gate, boundary, or progress
problem. The parent performs this capture itself using the current
`CODEX_THREAD_ID`; never instruct the external subagent to capture its own
session.

Capture automatically when any of these occurs:

- runner `status` is `error` or `partial`;
- `agent_status` is `PROTOCOL_ERROR`, or is `BLOCKED` with blocker,
  termination, concern, or observed-tool evidence pointing to the runner,
  grants, permission, protocol, evidence gate, role boundary, or progress
  behavior;
- termination reports timeout, stagnation, missing terminal truth, permission
  denial, structured-output/protocol failure, or incomplete required evidence;
- the external agent attempts an unauthorized, mutating, nested-agent, network,
  or otherwise out-of-role tool;
- a retry repeats without useful progress, useful edits exist without a clean
  terminal, or parent verification shows the reported outcome is inconsistent
  with observed files/tests/activity;
- `DONE_WITH_CONCERNS` includes a concern about the runner, grants, exposed
  tools, evidence collection, timeout/progress behavior, or output protocol.

Do not auto-capture a normal `DONE`, an expected `NEEDS_CONTEXT` turn, or a
`DONE_WITH_CONCERNS` whose concerns are solely about application code or task
scope. A task-level `BLOCKED` caused only by a genuinely missing application
dependency, unresolved product decision, unavailable task input, or a correctly
enforced authority boundary is also not a MiniMax problem. `NEEDS_CONTEXT` is
expected only when it contains 1-3 task-necessary
questions that the parent can answer while preserving the same scope,
permissions, and grants. Repeated, irrelevant, out-of-scope, or authority-
expanding questions are a protocol/boundary problem and MUST trigger capture.
If an expected turn later reveals a runner problem, capture at that point.

Load and follow the installed `capture-minimax-session` skill, then invoke its
sanitizer script directly against the current main-thread session. MUST NOT
route capture through `run_subagent.py`, another external CLI, or a native
subagent. Verify the generated report and report its path. If
`CODEX_THREAD_ID` is unavailable during automatic capture, report the
diagnostic blocker without guessing the newest session and continue the main
task; do not request unrelated authority. Capture is diagnostic only: it does not authorize broader grants, a
retry, fallback, edits to either skill, or interruption of unrelated task
completion. Reinvoke after a later dispatch only when it adds a new problem or
new runner evidence; stable fingerprints deduplicate unchanged captures. If
the capture itself fails, report that failure without exposing raw rollout
content or replacing the original subagent outcome.

## Interpreting User Requests

Extract parameters from user's natural language request:

| Parameter | Source |
|-----------|--------|
| `--agent` | Agent name, or an explicit `.md`/`.txt` definition path; never pass a directory |
| `--prompt` | Task instruction part (excluding agent specification) |
| `--cwd` | Current working directory (absolute path) |
| `--cli` | Backend override explicitly requested by the user; otherwise omit |
| `--timeout` | Idle timeout explicitly requested by the user, converted to milliseconds; otherwise omit so the agent definition or global default applies |
| `--allow-command` | Exact Bash shell string explicitly authorized for a Claude-family `safe-edit` agent; repeat once per command and preserve its quoting exactly |
| `--allow-path` | File or directory pattern relative to `--cwd` that a Claude-family `safe-edit` agent may edit; repeat once per ownership path |
| `--dialogue` | Require the bounded task-state protocol for a fresh invocation |
| `--parent-answer-file` | Validated prior-turn answer artifact inside `--cwd`; repeat as needed and use only with `--dialogue` |
| `--tdd` | Inject the strict RED-GREEN-REFACTOR contract for a `safe-edit` writer |
| `--tdd-command` | The one exact command that must prove RED then GREEN; supply exactly once and grant identically with `--allow-command` |
| `--require-evidence-path` | Existing regular file inside `--cwd` that a Claude-family read-only dialogue agent must successfully inspect; repeat for mandatory owners/validators |

**Example**:
"Run code-reviewer on src/"
→ `--agent code-reviewer --prompt "Review src/" --cwd $(pwd)`

## Proportional Routing

Keep tiny, precision fixes in the parent when they depend on dense shared
context or when reloading that context costs more than the edit. Prefer an
external writer for a bounded implementation unit with clear file ownership
and enough independent work to justify a fresh context.

Dispatch a writer only when the implementation unit is ready: required runtime
identities, profiles, fixtures, and accepted contracts exist; one established
local pattern is named; owned paths are complete; and an exact focused
verification command is known. An explorer finding an unresolved capability,
missing sealed workflow/profile, or architecture decision is a stop signal for
implementation, not an invitation to let the writer guess. Resolve the gate or
keep the task in design/exploration.

For an explorer asked to make architecture, reuse-as-is, no-schema-change, or
compatibility conclusions, identify the known authority owners before dispatch
and pass each one as `--require-evidence-path`. Include the service/call path,
durable state schema or validator, and writer/recovery owner when those surfaces
affect the conclusion. If the owner files are not yet known, make the first run
discovery-only; do not accept a definitive architecture conclusion from that
run. A report cannot promote a material unresolved concern into an unconditional
summary.

This skill implements external delegation; it does not decide whether a task
must be delegated. When a higher-priority rule routes a bounded writer through
this skill, use the host `writer` definition and its configured external
backend. Do not silently replace that dispatch with a native write-capable
agent. Returning implementation to the parent is a parent workflow decision,
not a writer fallback inside this skill.

Do not automatically bundle implementation, the full regression suite, and a
Git commit into one external invocation. The parent should normally run final
verification and commit already-completed work. Delegate a commit only when an
autonomous checkpoint is itself part of the bounded task and its exact command
has been confirmed before dispatch. A denied cleanup or commit command must not
discard or obscure completed implementation.

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

Output (project definitions win by name; host definitions are merged when no
explicit `--agents-dir` or `SUB_AGENTS_DIR` is selected):
```json
{"agents": [{"name": "writer", "description": "Bounded writer..."}], "agents_dir": "/project/.agents", "fallback_agents_dir": "/home/user/.agents"}
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

### Step 2: Check Concurrent Writer Ownership

Before launching a write-capable agent, inspect every observable live native
agent and external Codex/MiniMax `run_subagent.py` or CLI process. For each
writer, recover its explicit ownership from status reports and repeated
`--allow-path` grants; do not infer ownership from `git status` or `git diff`
alone.

Compare the new writer's complete target file set with those grants:

- If the file sets are disjoint and are not tightly coupled, fresh-dispatch a
  new bounded writer CLI immediately when higher-priority repository rules
  allow same-working-tree concurrency. Do not wait merely because another
  writer or CLI is running.
- If a path overlaps, the files are tightly coupled, or an active writer's
  ownership cannot be determined, coordinate or wait before dispatch.
- Give every concurrent writer mutually exclusive repeated `--allow-path`
  grants. Keep verification and Git command grants task-scoped, and re-check
  ownership before staging or committing.

An existing CLI process is evidence of activity, not a reusable dialogue
session. Every independent writer task still uses a fresh invocation.

### Step 3: Execute Agent

```bash
python3 {SKILL_DIR}/scripts/run_subagent.py \
  --agent <name> \
  --prompt "<task>" \
  --cwd <absolute-path>
```

Append `--cli <backend>` when the user specifies a backend. Append
`--timeout <milliseconds>` when the user specifies a timeout.
`--agent writer` first resolves `<cwd>/.agents/writer.md`, then automatically
falls back to `~/.agents/writer.md` when no explicit definition directory was
selected. An explicit definition file is also accepted directly, for example
`--agent /home/user/.agents/writer.md`; the runner safely derives the containing
directory and definition name. Do not combine a definition path with
`--agents-dir`.
For a Claude-family `safe-edit` agent, append one `--allow-command <exact command>`
per authorized test or Git command. The runner exposes no Bash tool when this
list is empty, and rejects every Bash command not listed exactly.
Each grant must have valid shell quoting. The runner also parses it into argv
for diagnostics, but argv equivalence never authorizes a differently quoted
shell string. Copy the displayed exact grant rather than reconstructing it.
Treat the grant list as the complete shell plan. Do not ask the agent to inspect
Git unless the exact Git command is granted; `Read`/`Grep` cover ordinary file
self-review without a pipe, `head`, `tail`, `&&`, or invented test selector.
Append one `--allow-path <relative path>` per owned file or directory pattern;
at least one is required for `safe-edit`, and edits outside those paths are
denied non-interactively.
When strict TDD is selected, append `--tdd`, exactly one
`--tdd-command <exact focused test>` flag, and an identical `--allow-command`
grant. The runner rejects TDD mode without a `safe-edit` definition or when a
TDD command is not granted exactly. The injected contract requires the writer
to create the regression test, observe the intended RED with that command,
then edit production and rerun the same command for GREEN. Collection, lint,
import failure, or permission denial is not RED. If production edits already
exist without credible RED evidence, the writer must stop with
`NEEDS_CONTEXT`; a fresh invocation does not retroactively establish TDD.
The runner validates the mode and exact command grant, but it does not infer
RED/GREEN ordering from the provider event stream. The parent must verify the
reported commands and workspace diff before accepting `DONE`.
For a task that may require parent clarification, append `--dialogue`. If the
agent returns `NEEDS_CONTEXT`, write the answer to a UTF-8 artifact inside
`--cwd` and fresh-dispatch the same task with
`--dialogue --parent-answer-file <relative path>`. The answer artifact is
context only: never add it to `--allow-path`, and never place credentials in it.
For broad read-only mapping, append one
`--require-evidence-path <relative-file>` per known authority owner. This flag
requires a Claude-family read-only `--dialogue` invocation. Paths must be
existing regular non-symlink files inside `--cwd`. The runner counts only a
successful `Read` or file-scoped `Grep` of that exact file; mentioning it in the
report, globbing its directory, or a failed tool call does not satisfy the gate.

### Step 4: Handle Response

Parse JSON output and check the transport `status` field:

```json
{"result":"...","status":"success","transport_exit_code":0,"exit_code":0,"cli_exit_code":-15,"termination_reason":"terminal_event","cli":"claude"}
```

Treat status as three separate layers:

| Layer | Fields | Meaning |
|-------|--------|---------|
| Runner transport | `status`, `transport_exit_code`, `termination_reason` | Whether `run_subagent.py` produced a usable terminal outcome; its OS exit is 0 only for `success` |
| Child CLI process | `cli_exit_code` | Raw subprocess return code, including negative signals; `terminal_event` may intentionally stop the CLI after a complete result |
| Dialogue task | `agent_status` | `DONE`, `DONE_WITH_CONCERNS`, `NEEDS_CONTEXT`, `BLOCKED`, or `PROTOCOL_ERROR` when `--dialogue` is used or the safe-edit runner emits a blocker |
| Runner configuration | `runner_context` | Sanitized resolved `model`, `effort`, `permission`, `tools_mode`, and exposed `tools` for this invocation; `default` means the backend's default surface was not enumerated |

`exit_code` is the normalized outcome code: 0 for a successful transport, 124
for runner timeouts, 127 when the CLI is missing, and the abnormal child code
when no successful terminal result exists. A spontaneous signal such as 143
is an error; only a runner-authored `terminal_event` after a parsed terminal
result can combine transport success with a nonzero raw `cli_exit_code`. If the
child exits 0 without a usable terminal result, the runner returns
`status=error`, `exit_code=1`, `cli_exit_code=0`, and
`termination_reason=missing_terminal_result`; it does not misreport the child
as having exited 1. Claude-family `--dialogue` invocations use the CLI's
`--json-schema` transport contract and normalize the terminal
`structured_output`; invalid model output is retried by the CLI and ends as an
explicit structured-output error if it cannot converge. If that transport
emits a schema-valid `StructuredOutput` tool call and its matching successful
`tool_result` but omits the final result event before a clean exit, the runner
recovers the confirmed payload with
`termination_reason=structured_tool_result`. Unconfirmed calls, error tool
results, non-schema invocations, and nonzero exits remain errors. The legacy
envelope path remains available for non-Claude backends and compatibility: if
the child
exits 0 and its last complete assistant message ends with a
`<subagent_result>` envelope, the runner recovers it through
`termination_reason=assistant_envelope` and applies the same strict semantic
validation. Plain text, non-dialogue runs, and nonzero child exits remain
errors.

Dialogue results may also include the optional structured arrays
`concern_categories` and `evidence_categories`. Their values come from closed
enums in the JSON schema; legacy payloads that omit them remain valid. Use the
arrays for cross-session diagnostics and keep detailed task evidence in
`result` and `observed_evidence_paths`.

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

When mandatory evidence is missing, the runner overrides an otherwise
successful model result with `status=error`, `agent_status=BLOCKED`,
`termination_reason=evidence_incomplete`, and a structured blocker containing
required, observed, and missing paths. Fix the evidence scope or run a
discovery-only task; do not accept the model's architecture conclusion.

For `safe-edit`, the first permission denial terminates the child because a
fresh non-interactive invocation cannot change its grants. Three equivalent
non-permission tool errors still trigger the repeated-error guard. The runner
returns `status=error`, `agent_status=BLOCKED`, and a structured `blocker` with
the attempted command, exact grants, argv-equivalence diagnosis, and tool
error. Inspect task-owned artifacts before deciding on a retry: if the assigned
deliverables and evidence are already complete, verify/adopt them without
paying for another fresh context; retry only when an authorized grant change is
required to finish a missing deliverable.

Dialogue is bounded turn-taking, not an interactive subprocess. The runner
uses `stdin=DEVNULL` and no session persistence. Parent answer files must be
regular, non-symlink UTF-8 files inside `--cwd`, at most 64 KiB; the runner
records their SHA-256 digest in injected context. A parent answer never grants
commands, editable paths, or broader authority.

For configuration or credential errors, retry after the required external
configuration has changed.

**By exit_code** (when status is not `success`):

| exit_code | Meaning | Resolution |
|-----------|---------|------------|
| 124 | Timeout | Increase `--timeout` or simplify task |
| 127 | CLI not found | Install required CLI (claude, codex, etc.) |
| 1 | Runner/general error | Check `error`, `termination_reason`, and `blocker` |
| other | Abnormal child exit | Inspect `cli_exit_code`; do not infer task success from dialogue prose |

## Agent Definition Location

| Priority | Source | Path |
|----------|--------|------|
| 1 | Explicit definition file | `--agent /path/to/<name>.md` |
| 2 | CLI directory | `--agents-dir /path/to/.agents` |
| 3 | Environment variable | `$SUB_AGENTS_DIR` |
| 4 | Project | `{cwd}/.agents/` |
| 5 | Host fallback | `$SUB_AGENTS_HOST_DIR` or `~/.agents/` |

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
| `timeout` | Positive milliseconds (optional) | Per-agent transport idle timeout used when `--timeout` is omitted; Claude-family read-only and safe-edit runs also use the resolved timeout as their semantic-stagnation cap |
| `permission` | `read-only`, `safe-edit` (default), `yolo` | `read-only` for investigation, `safe-edit` for workspace edits, or `yolo` to bypass approvals and sandboxing |

For Claude-based transports (`claude`, `glm`, `kimi`, and `minimax`),
`read-only` uses `dontAsk`, disables settings inheritance and session
persistence, and exposes only `Read`, `Glob`, and `Grep`, plus the internal
`StructuredOutput` finalizer when `--dialogue` supplies a schema. It does not expose
shell, write, plan-transition, task, network, or MCP tools; an empty strict MCP
configuration prevents inherited MCP servers from reopening that surface.
`safe-edit` uses `dontAsk` and likewise disables inherited settings, sessions,
nested-agent, network, plan-transition, and MCP tools. It exposes `Read`,
`Glob`, `Grep`, `Write`, and `Edit` (plus the internal `StructuredOutput`
finalizer for schema-backed dialogue), but only repeated `--allow-path` rules
approve edits; Bash appears only when at least one exact `--allow-command` is
supplied. The runner also injects the resolved path and command grants into the
agent's system context, including diagnostic argv, so a quoting mismatch is
actionable and a denied unlisted command is not mistaken for Bash being
unavailable. The runner fail-fast threshold counts denied/error results, not
new tool IDs or repeated failure events as semantic progress. For read-only
Claude-family agents, a distinct tool request or successful tool result is
semantic progress; the same request repeated with only a new tool ID is not.
This keeps active exploration alive without letting identical heartbeats evade
the resolved agent timeout. Runtime progress heartbeats are intentionally no
more frequent than once per minute; poll an attached process at roughly that
cadence and do not echo unchanged heartbeat-only output into the parent
context. Use repeated flags for explicit ownership, focused tests,
and task-only Git commands the parent has authorized. Do not use `yolo` as a
workaround for a missing path or command grant.

Claude CLI is the transport and tool host for `minimax`; it does not make
Claude user-installed plugins or Superpowers available. The empty
`--setting-sources`, strict empty MCP config, and isolated system prompt are
intentional. Workflow disciplines required from an external model must be
supplied explicitly, such as `--tdd`, instead of enabling ambient Claude
settings.

## MiniMax Configuration

The `minimax` backend uses Claude CLI with MiniMax's Anthropic-compatible API.

- Set `MINIMAX_API_KEY`; `CLI_API_KEY` remains a legacy fallback. Environment variables take precedence over saved credentials.
- To persist credentials, store `MINIMAX_API_KEY=<key>` in `~/.config/sub-agents/credentials.env` with mode `600`. Set `SUB_AGENTS_CREDENTIALS_FILE` to override this path.
- The default endpoint is `https://api.minimax.io/anthropic`. Coding Plan keys with the `sk-cp-` prefix automatically use `https://api.minimaxi.com/anthropic`; set `MINIMAX_BASE_URL` only to override endpoint selection explicitly.
- The default model is `MiniMax-M3`. Set `model` in the agent frontmatter or `MINIMAX_MODEL` to override it.
