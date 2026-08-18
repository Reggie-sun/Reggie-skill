# Codex-Specific Notes

Prevents sandbox denial, timeout mismatch, and premature termination of quiet nested runs.

## Permission

Nested CLIs need access to Codex session state and external CLI binaries.
Start `run_subagent.py` with escalated sandbox permissions to avoid a known
fail-then-retry path, including:

- `Operation not permitted`
- failure to initialize Codex app-server or session state
- failure to access external CLI binaries

## Timeout and progress

- `--timeout` is a transport inactivity timeout, not a fixed wall-clock deadline.
- Claude-family read-only runs use the resolved agent/CLI timeout as their
  semantic-stagnation cap instead of a fixed 120-second override. A distinct
  `Read`, `Glob`, or `Grep` request counts
  as progress even before its result; the same request repeated with only a
  new tool ID does not. Repeated identical heartbeats or tool results also do
  not count. Safe-edit uses the same resolved timeout for this cap so
  legitimate long-running tools are not killed by a shorter fixed threshold.
- Safe-edit separately stops after three repeated same-tool permission denials
  or three equivalent tool errors. Failed tool results and re-quoted retries do
  not refresh semantic progress. A single ordinary tool error does not trigger
  this guard, and an in-flight long-running test is not a denial loop. Success
  from an unrelated tool or Bash argv family does not clear the denied family;
  successful execution of that same family does.
- Omit it to use the agent definition's `timeout`; otherwise the global default is `600000ms`.
- The global `writer` on this host uses `1800000ms` with high-effort implementation.
- Set the surrounding tool timeout high enough for the complete task; heartbeat output keeps the attached run observable.

Long nested runs are normal. Keep the command attached until one terminal
condition occurs:

- `run_subagent.py` exits and returns its final JSON response.
- The process exits before returning valid JSON.
- The configured timeout expires.

The runner emits safe activity and heartbeat lines on stderr without exposing
prompt or tool arguments. Continue waiting on the same run while activity is
reported. On idle timeout, use the returned partial text and last event before
deciding whether to fresh-dispatch with artifact-backed context, reshape, or
fall back. Claude-family execution uses no session persistence and cannot be
resumed.

## Command grants

`--allow-command` remains an exact shell-string authorization. The runner
validates shell quoting and publishes both the exact string and parsed argv in
the child system context. Parsed argv is diagnostic only: semantically
equivalent single/double quoting does not widen the allowlist. After a denial,
the child must return `BLOCKED` instead of guessing another spelling. If it
does not, the runner returns a structured blocker after the third equivalent
failure with the attempted command, exact grants, and mismatch classification.

For tiny or dense-context fixes, keep implementation in the parent. For a
bounded external write, prefer to let the parent own final verification and
commit so a denied commit grant cannot waste an otherwise completed change.

## Status truth

- `status`, `transport_exit_code`, and `termination_reason` describe the runner
  transport. `run_subagent.py` exits 0 only for transport success.
- `cli_exit_code` is the raw child return code. A signal is an error unless the
  runner sent it after parsing a complete terminal event; that case is marked
  `termination_reason=terminal_event` and normalized `exit_code=0`.
- A child exit of 0 without a parsed terminal result is a transport error with
  `termination_reason=missing_terminal_result`, normalized `exit_code=1`, and
  raw `cli_exit_code=0`; diagnostics must not describe it as child exit 1.
- Claude-family `--dialogue` invocations pass a strict `--json-schema` and read
  `structured_output` from the terminal result. If the model cannot satisfy the
  schema after the CLI's bounded retries, the CLI reports an explicit
  `error_max_structured_output_retries` result instead of ambiguous success.
- A clean schema-enabled exit may recover a `StructuredOutput` tool payload only
  after the stream observes its matching successful `tool_result`; this is
  reported as `termination_reason=structured_tool_result`. Missing, mismatched,
  or error tool results remain `missing_terminal_result`.
- The legacy envelope fallback remains bounded: a clean child exit whose last
  complete assistant message ends with `<subagent_result>` may recover through
  `termination_reason=assistant_envelope`; strict semantic normalization still
  rejects malformed or contradictory output. Non-dialogue/plain-text and
  nonzero-exit cases remain transport errors.
- `agent_status` describes the bounded dialogue task and never overrides a
  transport error. Runner-detected denial loops use `agent_status=BLOCKED`.

## Bounded dialogue

Use `--dialogue` when an external agent may need parent clarification. A
compliant response exposes additive `agent_status` without changing transport
`status`. For `NEEDS_CONTEXT`, answer in a validated file inside `--cwd` and
fresh-dispatch the same task with `--parent-answer-file`. This is turn-based
artifact exchange, not live stdin. The artifact cannot grant tools, paths, or
commands and must not contain credentials.

## Sub-Agent Execution

When running a sub-agent, operate as a broker: carry one run from start to terminal state.

### Allowed actions

1. Validate the requested agent
2. Start `run_subagent.py`
3. Stay attached to that run until a terminal condition occurs
4. Return the sub-agent result, or the failure/timeout outcome

### If the user asks a question mid-run

Answer briefly, then return to waiting on the same run.

## Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `Operation not permitted (os error 1)` | Sandbox restriction | Use escalated permissions |
| Tool call ends while runner heartbeats continue | Surrounding tool timeout is too short | Increase the surrounding tool timeout |
| `permission denied` on session files | Sandbox restriction | Use escalated permissions |
