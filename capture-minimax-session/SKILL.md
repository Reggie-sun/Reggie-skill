---
name: capture-minimax-session
description: Capture a completed or stably stopped Codex session's external MiniMax subagent activity into a sanitized Markdown diagnostic. Use when the user explicitly asks to record, capture, audit, summarize, or preserve MiniMax/sub-agents CLI behavior, or automatically from the main thread when the sub-agents skill detects a probable MiniMax runner, transport, permission, protocol, evidence-gate, boundary, timeout/progress, or result-truth problem.
---

# Capture MiniMax Session

Create a post-task diagnostic artifact from the session JSONL without copying raw prompts, commands, environment values, credentials, or full tool output.

## Workflow

1. Confirm the relevant MiniMax dispatch is complete or at a stable stopping point. This skill records history; it does not complete the task or modify `sub-agents`. For automatic problem capture, the main-thread agent invokes this skill itself after applying the trigger rules in `sub-agents/SKILL.md`; never delegate capture to the external subagent.
2. Resolve the session:
   - First distinguish automatic `sub-agents` problem capture from an explicit user-requested capture.
   - Automatic mode MUST use only the current `CODEX_THREAD_ID`. Ignore historical or supplied session IDs that merely appear in the task or conversation; they are not candidates for the current abnormal dispatch.
   - If `CODEX_THREAD_ID` is unavailable in automatic mode, report that the diagnostic could not be recorded, continue the parent task, and do not guess from the newest file when concurrent sessions may exist.
   - Explicit capture may use the session ID explicitly supplied by the user; otherwise use `CODEX_THREAD_ID`.
   - If neither exists during explicit capture, stop and request the exact session ID.
3. Run:

   ```bash
   python3 {SKILL_DIR}/scripts/capture_session.py --session-id <session-id>
   ```

   `{SKILL_DIR}` is the directory containing this `SKILL.md`.
   Invoke this script directly from the main thread. Never route capture through `run_subagent.py`, another external CLI, or a native subagent.
4. Read the generated report and verify:
   - the source session ID and rollout path are correct;
   - MiniMax terminal truth keeps `status`, `transport_exit_code`, `cli_exit_code`, `termination_reason`, and `agent_status` separate;
   - terminal rows show sanitized runner-resolved `model`, `effort`, `permission`, exposed tools, and closed diagnostic categories when the runner supplied them;
   - invocation rows contain only flag shape, counts, command families, prompt length, and prompt hash;
   - `Diagnostic Signals` separates activity/tool/evidence efficiency findings from terminal failures;
   - no prompt, exact command, API key, environment value, full JSONL line, or full provider result appears.
5. Report the output path and the most important runner-level signatures. Keep application-code conclusions separate from runner/skill optimization evidence.

## Output Location

Default reports are timestamped and written under:

```text
/home/reggie/.codex/session-diagnostics/minimax/<session-id>-<fingerprint>.md
```

Use `--output <path>` only when the user requests a specific destination. The script refuses to overwrite an existing report unless `--force` is explicit.

Default captures include a stable fingerprint over MiniMax invocations, activity, terminal truth, and failure categories. Capture time remains inside the report metadata. If the same session has no new MiniMax behavior, the script returns the existing report path instead of creating a duplicate report. Explicit `--output` remains an exact non-overwriting request unless `--force` is supplied.

## Diagnostic Signals

Treat these as optimization evidence, not proof of application-code failure:

- `tool_error_event`: one or more MiniMax tool results reported an error.
- `explorer_tool_mismatch`: an explorer-only capture requested shell or mutating tools.
- `long_activity_gap`: one external session had a gap of at least 60 seconds between activity events; distinguish normal reasoning/structured-output pauses from stagnation before changing timeouts.
- `zero_terminal_evidence`: a completed terminal reported no observed evidence paths in a capture whose invocations are all dialogue-enabled; mixed captures do not guess terminal ownership.
- `read_heavy_exploration`: at least 15 reads occurred at a `Read:Grep` ratio of 5:1 or greater; this is a search-strategy lead, not proof of inefficiency.
- `external_session_prefix_canonicalized`: a truncated external UUID was merged into its single matching full UUID; inspect transport chunk boundaries instead of counting it as another MiniMax session.

Use repeated signals across different session fingerprints to justify `sub-agents` changes. A single signal is a focused investigation lead, not an automatic authorization to change routing, permissions, timeouts, or prompts.

## Interpretation Boundaries

- An invocation record proves that `run_subagent.py` was requested, not that the backend started.
- A dynamically constructed runner command may expose strict runner activity/process framing without a safely parseable flag shape. Associate its activity and terminal truth, but report the dynamic command shape instead of inventing `agent`, `cwd`, prompt, or grant fields.
- Activity events prove observed provider/runner events, not task correctness.
- `status=success` is transport truth; use `agent_status` for the dialogue task state.
- A missing terminal result remains unresolved; do not infer success from prose or edits.
- Repeated prompt hashes suggest a retry, but do not prove the retry was unjustified.
- Capture fingerprints intentionally ignore unrelated later JSONL growth when MiniMax invocation, activity, terminal, and failure data are unchanged.
- Capture fingerprints include the report schema version, so a changed analysis algorithm produces a fresh report instead of reusing stale diagnostics.
- Terminal rows come only from a schema-valid final runner envelope associated with the original invocation or its attached process polls; provider prose is not terminal truth.
- Cell-wrapped transport output is trusted only when a top-level exact runner/poll `cell ID` marker links forward to one unique `wait` call and its later result. A subsequent poll additionally requires an attached process ID or an external session matching the selected runner chain under the same unique-prefix rule. Nested stdout markers, reused cell IDs, reversed ordering, arbitrary waits, and ambiguous session prefixes are not runner evidence.
- A truncated external session token is canonicalized only when it is at least 24 characters and is the unique strict prefix of one full UUID in the same capture. Ambiguous prefixes remain separate.
- `runner_context` contains only strict runner-owned identifiers. `tools_mode=explicit` lists the enforced tool surface; `tools_mode=default` means the backend default was not enumerated. Historical terminals without context render these fields as `unknown`; the capture never infers them from provider prose.
- `concern_categories` and `evidence_categories` are closed categorical signals. Unknown historical values collapse to `other` instead of being copied verbatim.
- Error output is reduced to allowlisted categories such as `protocol` or `evidence_incomplete`; exact error prose is never copied.
- The report intentionally omits semantic task output. Re-open the source session narrowly if a specific optimization hypothesis requires more evidence.

## Safety

- Never `cat` or broadly `rg` the whole rollout into model context.
- Never add `--include-raw`, raw-prompt, raw-command, or environment-dump behavior.
- Never persist credentials found in historical output.
- Reports are limited to `2,000,000` UTF-8 bytes and fully written to a same-directory `600` temporary file before atomic publication. Reuse validates the complete report header, session, schema, fingerprint, completion marker, actual byte limit, regular-file type, and exact `600` mode through a no-follow descriptor. `--force` never follows an output symlink.
- Do not automatically edit, commit, or push `sub-agents` after capture. Optimization is a separate user-authorized task with its own tests, paid MiniMax gate, and native review.
