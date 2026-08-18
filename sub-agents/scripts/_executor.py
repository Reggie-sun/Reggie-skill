from __future__ import annotations

import os
import queue
import signal
import shutil
import subprocess
import sys
import tempfile
import threading
import time

from _builder import AgentInvocation, build_invocation_args
from _constants import DEFAULT_TIMEOUT_MS
from _stream import StreamProcessor

_SEMANTIC_PROGRESS_CLIS = frozenset({"claude", "glm", "kimi", "minimax"})
_MAX_STAGNATION_MS = 120_000


def _partial_response(
    cli: str,
    result: dict | None,
    exit_code: int,
    error: str,
    *,
    cli_exit_code: int | None = None,
    termination_reason: str,
) -> dict:
    response = {
        "result": result.get("result", "") if result else "",
        "exit_code": exit_code,
        "transport_exit_code": 1,
        "cli_exit_code": cli_exit_code,
        "status": "partial" if result else "error",
        "cli": cli,
        "termination_reason": termination_reason,
        "error": error,
    }
    if result:
        for key in ("session_id", "last_event"):
            if result.get(key) is not None:
                response[key] = result[key]
    return response


def _error_response(
    cli: str,
    exit_code: int,
    error: str,
    partial_result: dict | None = None,
    *,
    cli_exit_code: int | None = None,
    termination_reason: str = "runner_error",
) -> dict:
    return {
        "result": partial_result.get("result", "") if partial_result else "",
        "exit_code": exit_code,
        "transport_exit_code": 1,
        "cli_exit_code": cli_exit_code,
        "status": "error",
        "cli": cli,
        "termination_reason": termination_reason,
        "error": error,
    }


def build_final_response(
    cli: str,
    returncode: int | None,
    result: dict | None,
    stdout_lines: list,
    stderr: str,
    terminated_by_us: bool = False,
) -> dict:
    """Build transport truth separately from the raw child CLI exit."""
    cli_exit_code = returncode if returncode is not None else 1

    if result and (result.get("status") == "error" or result.get("is_error") is True):
        status = "error"
    elif result and result.get("status") == "partial":
        status = "partial"
    elif result and terminated_by_us:
        status = "success"
    elif result and cli_exit_code == 0:
        status = "success"
    else:
        status = "error"

    if terminated_by_us:
        termination_reason = "terminal_event"
    elif result and result.get("terminal_source") == "assistant_envelope":
        termination_reason = "assistant_envelope"
    elif not result and cli_exit_code == 0:
        termination_reason = "missing_terminal_result"
    elif cli_exit_code == 0:
        termination_reason = "cli_exit"
    elif cli_exit_code < 0 or cli_exit_code >= 128:
        termination_reason = "cli_signal"
    else:
        termination_reason = "cli_error"

    if status == "success":
        exit_code = 0
        transport_exit_code = 0
    else:
        exit_code = cli_exit_code if cli_exit_code != 0 else 1
        if terminated_by_us:
            exit_code = 1
        transport_exit_code = 1

    response = {
        "result": result.get("result", "") if result else "".join(stdout_lines),
        "exit_code": exit_code,
        "transport_exit_code": transport_exit_code,
        "cli_exit_code": cli_exit_code,
        "status": status,
        "cli": cli,
        "termination_reason": termination_reason,
    }
    if result and isinstance(result.get("structured_output"), dict):
        response["structured_output"] = result["structured_output"]
    if status == "error":
        result_error = result.get("error") if result else None
        result_subtype = result.get("subtype") if result else None
        result_text = result.get("result") if result else None
        if not terminated_by_us and cli_exit_code != 0 and result and not (
            result.get("status") == "error" or result.get("is_error") is True
        ):
            msg = f"CLI exited abnormally with code {cli_exit_code} after emitting a result"
        elif isinstance(result_error, str) and result_error.strip():
            msg = result_error.strip()
        elif isinstance(result_subtype, str) and result_subtype.startswith("error_"):
            msg = f"CLI reported {result_subtype.strip()}"
        elif isinstance(result_text, str) and result_text.strip():
            msg = result_text.strip()
        elif result:
            msg = "CLI reported an error"
        elif cli_exit_code == 0:
            msg = "CLI exited with code 0 without a usable terminal result"
        else:
            msg = f"CLI exited with code {exit_code}"
        if stderr and stderr.strip():
            msg += f": {stderr.strip()}"
        response["error"] = msg
    return response


_LINE = "line"
_EOF = "eof"

# Bound captured output to prevent an unending stream from exhausting memory.
_MAX_STDOUT_CHARS = 64 * 1024 * 1024


def _spawn_reader(process: subprocess.Popen) -> queue.Queue:
    """Read stdout in a daemon thread so the main loop can enforce timeouts."""
    line_q: queue.Queue = queue.Queue()

    def reader() -> None:
        try:
            for line in iter(process.stdout.readline, ""):
                line_q.put((_LINE, line))
        finally:
            line_q.put((_EOF, None))

    threading.Thread(target=reader, daemon=True).start()
    return line_q


def _timeout_payload(
    cli: str,
    processor: StreamProcessor,
    timeout_ms: int,
    cli_exit_code: int | None,
) -> dict:
    error = (
        f"Sub-agent idle timeout after {timeout_ms} ms without CLI activity. "
        "Increase --timeout, resume the reported session, or simplify the task before retrying."
    )
    return _partial_response(
        cli,
        processor.get_partial_result(),
        124,
        error,
        cli_exit_code=cli_exit_code,
        termination_reason="idle_timeout",
    )


def _stagnation_payload(
    cli: str,
    processor: StreamProcessor,
    timeout_ms: int,
    cli_exit_code: int | None,
) -> dict:
    error = (
        f"Sub-agent stagnation timeout after {timeout_ms} ms without semantic progress. "
        "Retry with a narrower task or lower reasoning effort."
    )
    return _partial_response(
        cli,
        processor.get_partial_result(),
        124,
        error,
        cli_exit_code=cli_exit_code,
        termination_reason="semantic_stagnation",
    )


def _tool_error_loop_payload(
    cli: str,
    processor: StreamProcessor,
    blocker: dict,
    cli_exit_code: int | None,
) -> dict:
    attempted = blocker.get("attempted_command") or "<unavailable>"
    if blocker.get("kind") == "permission_denial_loop":
        grant_match = blocker.get("grant_match")
        if blocker.get("tool") == "Bash" and grant_match in {
            "argv_equivalent_exact_string_mismatch",
            "command_not_authorized",
        }:
            detail = (
                f"Permission denial loop after {blocker['occurrences']} failures; "
                f"command grant mismatch for {attempted!r} ({grant_match})."
            )
        elif blocker.get("tool") == "Bash" and grant_match == "exact_grant_present":
            detail = (
                f"Permission denial loop after {blocker['occurrences']} failures; "
                f"the exact granted command {attempted!r} was denied by the CLI tool policy."
            )
        else:
            detail = (
                f"Permission denial loop after {blocker['occurrences']} failures "
                f"for tool {blocker.get('tool') or '<unknown>'}."
            )
    else:
        detail = (
            f"Repeated equivalent tool error after {blocker['occurrences']} failures "
            f"while attempting {attempted!r}."
        )
    response = _error_response(
        cli,
        1,
        detail,
        partial_result=processor.get_partial_result(),
        cli_exit_code=cli_exit_code,
        termination_reason="tool_error_loop",
    )
    response.update(
        {
            "agent_status": "BLOCKED",
            "summary": detail,
            "blocker": blocker,
        }
    )
    return response


def _signal_process_group(process: subprocess.Popen, sig: int) -> bool:
    try:
        os.killpg(process.pid, sig)
        return True
    except ProcessLookupError:
        return False
    except OSError:
        # Retain a best-effort fallback for unusual platforms/process launchers.
        if process.poll() is not None:
            return False
        try:
            process.send_signal(sig)
            return True
        except ProcessLookupError:
            return False


def _terminate_after_terminal(process: subprocess.Popen, grace_sec: float = 0.05) -> bool:
    """Let a CLI report its own exit before attributing a SIGTERM to the runner."""
    try:
        process.wait(timeout=grace_sec)
        # The leader reported its own exit; still clean up any inherited group.
        _signal_process_group(process, signal.SIGTERM)
        return False
    except subprocess.TimeoutExpired:
        return _signal_process_group(process, signal.SIGTERM)


def _emit_progress(
    stream,
    cli: str,
    kind: str,
    event: str,
    started_at: float,
    session_id: str | None,
) -> None:
    elapsed = int(time.monotonic() - started_at)
    session = f" session={session_id}" if session_id else ""
    print(
        f"[sub-agent] {kind} cli={cli} elapsed={elapsed}s event={event}{session}",
        file=stream,
        flush=True,
    )


def _drain_to_eof(line_q: queue.Queue, budget_sec: float = 0.5) -> None:
    """Drain stdout to prevent concurrent reads during ``communicate()``."""
    deadline = time.monotonic() + budget_sec
    while time.monotonic() < deadline:
        try:
            kind, _ = line_q.get(timeout=0.05)
        except queue.Empty:
            return
        if kind == _EOF:
            return


def _drive_process(
    process: subprocess.Popen,
    cli: str,
    timeout_ms: int,
    heartbeat_sec: float = 30.0,
    progress_stream=None,
    max_stdout_chars: int = _MAX_STDOUT_CHARS,
    semantic_timeout_ms: int | None = None,
    allowed_commands: tuple[str, ...] = (),
    fail_fast_tool_errors: bool = False,
    allow_dialogue_fallback: bool = False,
    allow_structured_output: bool = False,
) -> dict:
    if progress_stream is None:
        progress_stream = sys.stderr
    started_at = time.monotonic()
    idle_deadline = started_at + timeout_ms / 1000
    if semantic_timeout_ms is None:
        stagnation_timeout_ms = (
            _MAX_STAGNATION_MS if cli in _SEMANTIC_PROGRESS_CLIS else 0
        )
    else:
        stagnation_timeout_ms = semantic_timeout_ms
    stagnation_deadline = started_at + stagnation_timeout_ms / 1000
    enforce_stagnation = stagnation_timeout_ms > 0
    next_heartbeat = started_at + heartbeat_sec
    processor = StreamProcessor(
        cli,
        allowed_commands=allowed_commands,
        count_tool_requests_as_progress=not fail_fast_tool_errors,
        allow_structured_output=allow_structured_output,
    )
    stdout_lines: list = []
    accumulated_chars = 0
    line_q = _spawn_reader(process)
    saw_terminal = False
    terminated_by_us = False
    last_progress_event = None
    last_progress_revision = processor.get_progress_revision()

    try:
        while True:
            now = time.monotonic()
            active_deadline = min(idle_deadline, stagnation_deadline) if enforce_stagnation else idle_deadline
            remaining = active_deadline - now
            if remaining <= 0:
                _signal_process_group(process, signal.SIGKILL)
                _drain_to_eof(line_q)
                process.communicate()
                if enforce_stagnation and stagnation_deadline <= idle_deadline:
                    return _stagnation_payload(
                        cli, processor, stagnation_timeout_ms, process.returncode
                    )
                return _timeout_payload(cli, processor, timeout_ms, process.returncode)

            try:
                wait_for = min(remaining, max(0.001, next_heartbeat - now))
                kind, line = line_q.get(timeout=wait_for)
            except queue.Empty:
                now = time.monotonic()
                if now >= idle_deadline:
                    _signal_process_group(process, signal.SIGKILL)
                    _drain_to_eof(line_q)
                    process.communicate()
                    return _timeout_payload(cli, processor, timeout_ms, process.returncode)
                if enforce_stagnation and now >= stagnation_deadline:
                    _signal_process_group(process, signal.SIGKILL)
                    _drain_to_eof(line_q)
                    process.communicate()
                    return _stagnation_payload(
                        cli, processor, stagnation_timeout_ms, process.returncode
                    )
                event, session_id = processor.get_progress()
                _emit_progress(
                    progress_stream, cli, "heartbeat", event, started_at, session_id
                )
                next_heartbeat = now + heartbeat_sec
                continue

            if kind == _EOF:
                break
            idle_deadline = time.monotonic() + timeout_ms / 1000
            next_heartbeat = time.monotonic() + heartbeat_sec
            stdout_lines.append(line)
            accumulated_chars += len(line)
            if not saw_terminal and accumulated_chars > max_stdout_chars:
                _signal_process_group(process, signal.SIGKILL)
                _drain_to_eof(line_q)
                process.communicate()
                return _error_response(
                    cli,
                    1,
                    f"Sub-agent output exceeded {max_stdout_chars} characters. "
                    "Retry with a narrower task.",
                    partial_result=processor.get_result(),
                    cli_exit_code=process.returncode,
                    termination_reason="output_limit",
                )
            if not saw_terminal:
                terminal = processor.process_line(line)
                blocker = (
                    processor.get_tool_error_loop() if fail_fast_tool_errors else None
                )
                event, session_id = processor.get_progress()
                progress_revision = processor.get_progress_revision()
                if progress_revision != last_progress_revision:
                    stagnation_deadline = time.monotonic() + stagnation_timeout_ms / 1000
                    last_progress_revision = progress_revision
                if event != last_progress_event:
                    _emit_progress(
                        progress_stream, cli, "activity", event, started_at, session_id
                    )
                    last_progress_event = event
                if blocker is not None:
                    _signal_process_group(process, signal.SIGKILL)
                    _drain_to_eof(line_q)
                    process.communicate()
                    return _tool_error_loop_payload(
                        cli, processor, blocker, process.returncode
                    )
                if terminal:
                    terminated_by_us = _terminate_after_terminal(process)
                    saw_terminal = True

        # Allow a short graceful-exit window before killing the process.
        wait_remaining = max(0.1, idle_deadline - time.monotonic())
        try:
            _, stderr = process.communicate(timeout=wait_remaining)
        except subprocess.TimeoutExpired:
            _signal_process_group(process, signal.SIGKILL)
            _, stderr = process.communicate()
            return _timeout_payload(cli, processor, timeout_ms, process.returncode)

        result = processor.get_result()
        if result is None:
            processor.process_complete_output("".join(stdout_lines))
            result = processor.get_result()
        if result is None and process.returncode == 0 and allow_dialogue_fallback:
            processor.promote_clean_exit_dialogue_result()
            result = processor.get_result()

        return build_final_response(
            cli,
            process.returncode,
            result,
            stdout_lines,
            stderr,
            terminated_by_us=terminated_by_us,
        )
    except (OSError, ValueError) as e:
        _signal_process_group(process, signal.SIGKILL)
        # Reap before callers clean up per-run resources.
        process.wait()
        return _error_response(
            cli,
            1,
            f"{type(e).__name__}: {e}",
            partial_result=processor.get_result(),
            cli_exit_code=process.returncode,
        )


def _build_proc_env(env_override: dict | None) -> dict | None:
    """Apply child environment overrides; ``None`` removes a variable."""
    if not env_override:
        return None
    proc_env = {**os.environ}
    for key, value in env_override.items():
        if value is None:
            proc_env.pop(key, None)
        else:
            proc_env[key] = value
    return proc_env


def _spawn_and_drive(
    command: str,
    args: list,
    proc_env: dict | None,
    cwd: str,
    cli: str,
    timeout_ms: int,
    heartbeat_sec: float = 30.0,
    progress_stream=None,
    max_stdout_chars: int = _MAX_STDOUT_CHARS,
    semantic_timeout_ms: int | None = None,
    allowed_commands: tuple[str, ...] = (),
    fail_fast_tool_errors: bool = False,
    allow_dialogue_fallback: bool = False,
    allow_structured_output: bool = False,
) -> dict:
    try:
        # Prevent CLIs from waiting for interactive input.
        process = subprocess.Popen(
            [command, *args],
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            # CLI streams are UTF-8 regardless of host locale.
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=proc_env,
            start_new_session=True,
        )
    except FileNotFoundError:
        return _error_response(
            cli,
            127,
            f"CLI unavailable: {command!r} was not found on PATH. "
            "Install it or select another backend.",
        )
    except OSError as e:
        return _error_response(cli, 1, f"{type(e).__name__}: {e}")

    return _drive_process(
        process,
        cli,
        timeout_ms,
        heartbeat_sec=heartbeat_sec,
        progress_stream=progress_stream,
        max_stdout_chars=max_stdout_chars,
        semantic_timeout_ms=semantic_timeout_ms,
        allowed_commands=allowed_commands,
        fail_fast_tool_errors=fail_fast_tool_errors,
        allow_dialogue_fallback=allow_dialogue_fallback,
        allow_structured_output=allow_structured_output,
    )


def _isolated_opencode_env(env_override: dict | None, temp_dir: str) -> dict:
    """Isolate OpenCode state to prevent concurrent SQLite session locks."""
    data_home = os.path.join(temp_dir, "data")
    state_home = os.path.join(temp_dir, "state")
    os.makedirs(os.path.join(data_home, "opencode"))
    os.makedirs(state_home)

    default_data_home = os.environ.get(
        "XDG_DATA_HOME", os.path.join(os.path.expanduser("~"), ".local", "share")
    )
    auth_file = os.path.join(default_data_home, "opencode", "auth.json")
    try:
        if os.path.isfile(auth_file):
            shutil.copy2(auth_file, os.path.join(data_home, "opencode", "auth.json"))
    except OSError:
        # OpenCode reports authentication failures when this copy was required.
        pass

    return {**(env_override or {}), "XDG_DATA_HOME": data_home, "XDG_STATE_HOME": state_home}


def execute_agent(
    inv: AgentInvocation,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    *,
    allow_dialogue_fallback: bool = False,
) -> dict:
    command, args, env_override = build_invocation_args(inv)

    if inv.cli == "opencode":
        temp_dir = tempfile.mkdtemp(prefix="subagent-opencode-")
        try:
            proc_env = _build_proc_env(_isolated_opencode_env(env_override, temp_dir))
            return _spawn_and_drive(command, args, proc_env, inv.cwd, inv.cli, timeout_ms)
        finally:
            # _spawn_and_drive reaps the process before returning.
            shutil.rmtree(temp_dir, ignore_errors=True)

    proc_env = _build_proc_env(env_override)
    return _spawn_and_drive(
        command,
        args,
        proc_env,
        inv.cwd,
        inv.cli,
        timeout_ms,
        semantic_timeout_ms=(
            timeout_ms
            if inv.permission == "safe-edit" or inv.cli in _SEMANTIC_PROGRESS_CLIS
            else None
        ),
        allowed_commands=inv.allowed_commands,
        fail_fast_tool_errors=inv.permission == "safe-edit",
        allow_dialogue_fallback=allow_dialogue_fallback,
        allow_structured_output=inv.structured_output_schema is not None,
    )
