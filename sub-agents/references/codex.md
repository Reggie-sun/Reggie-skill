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
- Claude-family runs also stop after 120 seconds without new text or distinct
  tool activity; repeated identical heartbeats or tool results do not count as
  progress.
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
reported. On idle timeout, use the returned partial text, session id, and last
event before deciding whether to resume, reshape, or fall back.

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
