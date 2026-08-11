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

# SIGTERM may be reported as 143 or -15.
_SUCCESS_EXIT_CODES = (0, 143, -15)
_SEMANTIC_PROGRESS_CLIS = frozenset({"claude", "glm", "kimi", "minimax"})
_MAX_STAGNATION_MS = 120_000


def _partial_response(cli: str, result: dict | None, exit_code: int, error: str) -> dict:
    response = {
        "result": result.get("result", "") if result else "",
        "exit_code": exit_code,
        "status": "partial" if result else "error",
        "cli": cli,
        "error": error,
    }
    if result:
        for key in ("session_id", "last_event"):
            if result.get(key) is not None:
                response[key] = result[key]
    return response


def _error_response(
    cli: str, exit_code: int, error: str, partial_result: dict | None = None
) -> dict:
    return {
        "result": partial_result.get("result", "") if partial_result else "",
        "exit_code": exit_code,
        "status": "error",
        "cli": cli,
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
    """Build a response, treating intentional termination as success."""
    exit_code = returncode if returncode is not None else 1

    if result and (result.get("status") == "error" or result.get("is_error") is True):
        status = "error"
    elif result and result.get("status") == "partial":
        status = "partial"
    elif result and (terminated_by_us or exit_code in _SUCCESS_EXIT_CODES):
        status = "success"
    elif result:
        status = "partial"
    else:
        status = "error"

    response = {
        "result": result.get("result", "") if result else "".join(stdout_lines),
        "exit_code": exit_code,
        "status": status,
        "cli": cli,
    }
    if status == "error":
        result_error = result.get("error") if result else None
        result_subtype = result.get("subtype") if result else None
        result_text = result.get("result") if result else None
        if isinstance(result_error, str) and result_error.strip():
            msg = result_error.strip()
        elif isinstance(result_subtype, str) and result_subtype.startswith("error_"):
            msg = f"CLI reported {result_subtype.strip()}"
        elif isinstance(result_text, str) and result_text.strip():
            msg = result_text.strip()
        elif result:
            msg = "CLI reported an error"
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


def _timeout_payload(cli: str, processor: StreamProcessor, timeout_ms: int) -> dict:
    error = (
        f"Sub-agent idle timeout after {timeout_ms} ms without CLI activity. "
        "Increase --timeout, resume the reported session, or simplify the task before retrying."
    )
    return _partial_response(cli, processor.get_partial_result(), 124, error)


def _stagnation_payload(cli: str, processor: StreamProcessor, timeout_ms: int) -> dict:
    error = (
        f"Sub-agent stagnation timeout after {timeout_ms} ms without semantic progress. "
        "Retry with a narrower task or lower reasoning effort."
    )
    return _partial_response(cli, processor.get_partial_result(), 124, error)


def _signal_process_group(process: subprocess.Popen, sig: int) -> None:
    try:
        os.killpg(process.pid, sig)
    except ProcessLookupError:
        return
    except OSError:
        # Retain a best-effort fallback for unusual platforms/process launchers.
        if process.poll() is not None:
            return
        try:
            process.send_signal(sig)
        except ProcessLookupError:
            pass


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
) -> dict:
    if progress_stream is None:
        progress_stream = sys.stderr
    started_at = time.monotonic()
    idle_deadline = started_at + timeout_ms / 1000
    stagnation_timeout_ms = _MAX_STAGNATION_MS
    stagnation_deadline = started_at + stagnation_timeout_ms / 1000
    enforce_stagnation = cli in _SEMANTIC_PROGRESS_CLIS
    next_heartbeat = started_at + heartbeat_sec
    processor = StreamProcessor(cli)
    stdout_lines: list = []
    accumulated_chars = 0
    line_q = _spawn_reader(process)
    saw_terminal = False
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
                    return _stagnation_payload(cli, processor, stagnation_timeout_ms)
                return _timeout_payload(cli, processor, timeout_ms)

            try:
                wait_for = min(remaining, max(0.001, next_heartbeat - now))
                kind, line = line_q.get(timeout=wait_for)
            except queue.Empty:
                now = time.monotonic()
                if now >= idle_deadline:
                    _signal_process_group(process, signal.SIGKILL)
                    _drain_to_eof(line_q)
                    process.communicate()
                    return _timeout_payload(cli, processor, timeout_ms)
                if enforce_stagnation and now >= stagnation_deadline:
                    _signal_process_group(process, signal.SIGKILL)
                    _drain_to_eof(line_q)
                    process.communicate()
                    return _stagnation_payload(cli, processor, stagnation_timeout_ms)
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
                )
            if not saw_terminal:
                terminal = processor.process_line(line)
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
                if terminal:
                    _signal_process_group(process, signal.SIGTERM)
                    saw_terminal = True

        # Allow a short graceful-exit window before killing the process.
        wait_remaining = max(0.1, idle_deadline - time.monotonic())
        try:
            _, stderr = process.communicate(timeout=wait_remaining)
        except subprocess.TimeoutExpired:
            _signal_process_group(process, signal.SIGKILL)
            _, stderr = process.communicate()
            return _timeout_payload(cli, processor, timeout_ms)

        result = processor.get_result()
        if result is None:
            processor.process_complete_output("".join(stdout_lines))
            result = processor.get_result()

        return build_final_response(
            cli,
            process.returncode,
            result,
            stdout_lines,
            stderr,
            terminated_by_us=saw_terminal,
        )
    except (OSError, ValueError) as e:
        _signal_process_group(process, signal.SIGKILL)
        # Reap before callers clean up per-run resources.
        process.wait()
        return _error_response(
            cli, 1, f"{type(e).__name__}: {e}", partial_result=processor.get_result()
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


def execute_agent(inv: AgentInvocation, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> dict:
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
    return _spawn_and_drive(command, args, proc_env, inv.cwd, inv.cli, timeout_ms)
