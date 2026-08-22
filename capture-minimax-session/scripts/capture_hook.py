#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable


PENDING_ROOT = Path("/home/reggie/.codex/session-diagnostics/minimax/.pending")
CAPTURE_SCRIPT = Path(__file__).with_name("capture_session.py")
RUNNER_SCRIPT = Path(__file__).resolve().parents[2] / "sub-agents/scripts/run_subagent.py"
SESSION_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
ALLOWED_REASONS = frozenset(
    {
        "permission_or_tooling",
        "protocol_or_output",
        "evidence_gap",
        "runner_blocked",
        "timeout_or_performance",
        "transport_error",
        "transport_partial",
    }
)
MAX_HOOK_INPUT_BYTES = 1_000_000
MAX_TOOL_OUTPUT_BYTES = 2_000_000
MAX_MARKER_BYTES = 4096
CAPTURE_TIMEOUT_SECONDS = 60


def _open_pending_dir(pending_root: Path, *, create: bool) -> int | None:
    try:
        if create:
            pending_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(
            pending_root,
            os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
        )
    except OSError:
        return None
    metadata = os.fstat(fd)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) & 0o077
    ):
        os.close(fd)
        return None
    return fd


def _is_runner_command(command: object) -> bool:
    if not isinstance(command, str) or len(command) > 1_000_000:
        return False
    command = command.replace("\\\r\n", "").replace("\\\n", "")
    if "\n" in command or "\r" in command:
        return False
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        lexer.commenters = ""
        tokens = list(lexer)
    except ValueError:
        return False
    if any(token and set(token) <= set("();<>|&") for token in tokens):
        return False
    if len(tokens) < 2 or Path(tokens[0]).name not in {"python", "python3"}:
        return False
    try:
        return Path(tokens[1]).resolve(strict=True) == RUNNER_SCRIPT.resolve(strict=True)
    except OSError:
        return False


def _closed_reasons(value: object) -> list[str] | None:
    if not isinstance(value, list) or not value:
        return None
    if not all(isinstance(reason, str) and reason in ALLOWED_REASONS for reason in value):
        return None
    return list(dict.fromkeys(value))


def _terminal_capture_reasons(tool_response: object) -> list[str] | None:
    if isinstance(tool_response, str):
        output = tool_response
    elif isinstance(tool_response, dict):
        output = tool_response.get("output")
    else:
        return None
    if not isinstance(output, str) or len(output.encode("utf-8")) > MAX_TOOL_OUTPUT_BYTES:
        return None
    for line in reversed(output.splitlines()):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict) or payload.get("cli") != "minimax":
            continue
        capture = payload.get("automatic_capture")
        if not isinstance(capture, dict) or capture.get("required") is not True:
            return None
        return _closed_reasons(capture.get("reasons"))
    return None


def _publish_marker(
    pending_root: Path,
    session_id: str,
    tool_use_id: object,
    reasons: list[str],
) -> Path | None:
    directory_fd = _open_pending_dir(pending_root, create=True)
    if directory_fd is None:
        return None
    tool_digest = hashlib.sha256(str(tool_use_id).encode("utf-8")).hexdigest()[:16]
    name = f"{session_id}-{time.time_ns()}-{tool_digest}.json"
    file_fd: int | None = None
    try:
        file_fd = os.open(
            name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=directory_fd,
        )
        os.fchmod(file_fd, 0o600)
        payload = json.dumps(
            {"session_id": session_id, "reasons": reasons},
            sort_keys=True,
        ).encode("utf-8") + b"\n"
        remaining = memoryview(payload)
        while remaining:
            written = os.write(file_fd, remaining)
            if written <= 0:
                raise OSError("short marker write")
            remaining = remaining[written:]
        os.fsync(file_fd)
        os.close(file_fd)
        file_fd = None
        os.fsync(directory_fd)
        return pending_root / name
    except OSError:
        if file_fd is not None:
            os.close(file_fd)
        try:
            os.unlink(name, dir_fd=directory_fd)
        except OSError:
            pass
        return None
    finally:
        os.close(directory_fd)


def process_post_tool_event(
    event: dict,
    *,
    pending_root: Path = PENDING_ROOT,
) -> Path | None:
    if (
        event.get("hook_event_name") != "PostToolUse"
        or event.get("tool_name") != "Bash"
    ):
        return None
    session_id = event.get("session_id")
    if not isinstance(session_id, str) or not SESSION_ID_RE.fullmatch(session_id):
        return None
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict) or not _is_runner_command(tool_input.get("command")):
        return None
    reasons = _terminal_capture_reasons(event.get("tool_response"))
    if reasons is None:
        return None
    return _publish_marker(pending_root, session_id, event.get("tool_use_id"), reasons)


def _claim_markers(session_id: str, pending_root: Path) -> tuple[int | None, list[str]]:
    directory_fd = _open_pending_dir(pending_root, create=False)
    if directory_fd is None:
        return None, []
    claims: list[str] = []
    prefix = f"{session_id}-"
    for name in sorted(os.listdir(directory_fd)):
        if not name.startswith(prefix) or not name.endswith(".json"):
            continue
        claim = f".{name[:-5]}.{os.getpid()}.{time.time_ns()}.claim"
        try:
            os.rename(
                name,
                claim,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
            )
        except OSError:
            continue
        valid = False
        try:
            file_fd = os.open(
                claim,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=directory_fd,
            )
        except OSError:
            pass
        else:
            try:
                metadata = os.fstat(file_fd)
                if (
                    stat.S_ISREG(metadata.st_mode)
                    and metadata.st_uid == os.getuid()
                    and stat.S_IMODE(metadata.st_mode) == 0o600
                    and metadata.st_size <= MAX_MARKER_BYTES
                ):
                    raw = os.read(file_fd, MAX_MARKER_BYTES + 1)
                    try:
                        payload = json.loads(raw.decode("utf-8"))
                    except (UnicodeError, json.JSONDecodeError):
                        payload = None
                    valid = (
                        isinstance(payload, dict)
                        and payload.get("session_id") == session_id
                        and _closed_reasons(payload.get("reasons")) is not None
                    )
            finally:
                os.close(file_fd)
        if valid:
            claims.append(claim)
        else:
            try:
                os.unlink(claim, dir_fd=directory_fd)
            except OSError:
                pass
    if not claims:
        os.close(directory_fd)
        return None, []
    return directory_fd, claims


def _run_capture(session_id: str) -> Path:
    completed = subprocess.run(
        [sys.executable, str(CAPTURE_SCRIPT), "--session-id", session_id],
        check=True,
        capture_output=True,
        text=True,
        timeout=CAPTURE_TIMEOUT_SECONDS,
    )
    output_lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if not output_lines:
        raise RuntimeError("capture produced no report path")
    report = Path(output_lines[-1])
    metadata = report.lstat()
    if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600:
        raise RuntimeError("capture report failed regular-file or mode validation")
    return report


def process_stop_event(
    event: dict,
    *,
    pending_root: Path = PENDING_ROOT,
    capture_runner: Callable[[str], Path] = _run_capture,
) -> dict | None:
    if event.get("hook_event_name") != "Stop":
        return None
    session_id = event.get("session_id")
    if not isinstance(session_id, str) or not SESSION_ID_RE.fullmatch(session_id):
        return None
    directory_fd, claims = _claim_markers(session_id, pending_root)
    if directory_fd is None:
        return None

    try:
        try:
            report = capture_runner(session_id)
            message = (
                "Automatic MiniMax diagnostic capture completed: "
                f"{report}. Report this path and the original subagent outcome, then finish the task."
            )
        except (OSError, RuntimeError, subprocess.SubprocessError):
            message = (
                "Automatic MiniMax diagnostic capture failed after a queued runner problem. "
                "Report the diagnostic failure without changing the original subagent outcome, "
                "then finish the task."
            )
    finally:
        for claim in claims:
            try:
                os.unlink(claim, dir_fd=directory_fd)
            except OSError:
                pass
        os.close(directory_fd)

    if event.get("stop_hook_active") is True:
        return {"continue": True, "systemMessage": message}
    return {"decision": "block", "reason": message}


def main() -> int:
    raw = sys.stdin.buffer.read(MAX_HOOK_INPUT_BYTES + 1)
    if len(raw) > MAX_HOOK_INPUT_BYTES:
        print(json.dumps({"continue": True}))
        return 0
    try:
        event = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        print(json.dumps({"continue": True}))
        return 0
    result = None
    if isinstance(event, dict):
        if event.get("hook_event_name") == "PostToolUse":
            process_post_tool_event(event)
        elif event.get("hook_event_name") == "Stop":
            result = process_stop_event(event)
    print(json.dumps(result or {"continue": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
