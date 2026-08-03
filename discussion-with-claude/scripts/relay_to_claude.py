#!/usr/bin/env python3
"""Send a read-only prompt to Claude and always return normalized JSON."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

MARKER_RE = re.compile(r"(?:<\|assistant\|>(?:</tool_call>)?)\s*$")
DEFAULT_TIMEOUT_SECONDS = 600
EXCERPT_LIMIT = 2000


def read_prompt(args: argparse.Namespace) -> str:
    if args.prompt_file:
        return Path(args.prompt_file).read_text(encoding="utf-8")
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return ""


def build_command(args: argparse.Namespace) -> list[str]:
    command = [
        "claude",
        "-p",
        "--output-format",
        "json",
        "--disable-slash-commands",
        "--allowedTools",
        "Read,Grep,Glob",
        "--disallowedTools",
        "Bash,Edit,Write",
    ]
    if args.resume:
        command.extend(["--resume", args.resume])
    return command


def clean_result(text: str) -> str:
    return MARKER_RE.sub("", text).strip()


def as_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def excerpt(value: str | bytes | None, limit: int = EXCERPT_LIMIT) -> str:
    text = as_text(value).strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit]}\n...[truncated]"


def parse_json_object(stdout: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        payload = json.loads(stdout)
        if isinstance(payload, dict):
            return payload, None
        return None, "Claude JSON root was not an object"
    except json.JSONDecodeError as exc:
        first_error = str(exc)

    decoder = json.JSONDecoder()
    candidate: dict[str, Any] | None = None
    for match in re.finditer(r"\{", stdout):
        try:
            payload, _ = decoder.raw_decode(stdout[match.start() :])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            candidate = payload
    if candidate is not None:
        return candidate, None
    return None, first_error


def make_payload(
    *,
    ok: bool,
    status: str,
    message: str,
    result: str = "",
    raw_result: Any = "",
    session_id: Any = None,
    stop_reason: Any = None,
    is_error: Any = None,
    returncode: int | None = None,
    stdout: str | bytes | None = None,
    stderr: str | bytes | None = None,
    suggested_exit_code: int = 0,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "status": status,
        "message": message,
        "session_id": session_id,
        "stop_reason": stop_reason,
        "result": result,
        "raw_result": raw_result,
        "is_error": is_error,
        "returncode": returncode,
        "suggested_exit_code": suggested_exit_code,
        "stdout_excerpt": excerpt(stdout),
        "stderr_excerpt": excerpt(stderr),
    }


def emit(payload: dict[str, Any], *, strict_exit: bool) -> int:
    json.dump(payload, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    if strict_exit:
        return int(payload.get("suggested_exit_code") or 0)
    return 0


def payload_from_claude_json(
    payload: dict[str, Any],
    *,
    status: str,
    message: str,
    ok: bool,
    returncode: int | None,
    stdout: str | bytes | None = None,
    stderr: str | bytes | None = None,
    suggested_exit_code: int = 0,
) -> dict[str, Any]:
    raw_result = payload.get("result", "")
    cleaned_result = clean_result(raw_result) if isinstance(raw_result, str) else ""
    if ok and payload.get("is_error"):
        ok = False
        status = "claude_error"
        message = "Claude returned is_error=true."
        suggested_exit_code = suggested_exit_code or 1
    if ok and not cleaned_result:
        ok = False
        status = "empty_result"
        message = "Claude returned successfully, but the result was empty."
        suggested_exit_code = suggested_exit_code or 1
    return make_payload(
        ok=ok,
        status=status,
        message=message,
        result=cleaned_result,
        raw_result=raw_result,
        session_id=payload.get("session_id"),
        stop_reason=payload.get("stop_reason"),
        is_error=payload.get("is_error"),
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        suggested_exit_code=suggested_exit_code,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Relay a read-only prompt to Claude and normalize the JSON response.",
    )
    parser.add_argument("--prompt-file", help="Read the prompt from a file.")
    parser.add_argument("--resume", help="Resume an existing Claude session id.")
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Maximum seconds to wait for Claude before failing fast (default: {DEFAULT_TIMEOUT_SECONDS}).",
    )
    parser.add_argument(
        "--strict-exit",
        action="store_true",
        help="Return non-zero for failure statuses. By default failures are reported as JSON with exit 0.",
    )
    args = parser.parse_args()

    try:
        prompt = read_prompt(args)
    except OSError as exc:
        return emit(
            make_payload(
                ok=False,
                status="prompt_error",
                message=f"Failed to read prompt: {exc}",
                suggested_exit_code=2,
            ),
            strict_exit=args.strict_exit,
        )
    if not prompt.strip():
        return emit(
            make_payload(
                ok=False,
                status="prompt_missing",
                message="Prompt is required via stdin or --prompt-file.",
                suggested_exit_code=2,
            ),
            strict_exit=args.strict_exit,
        )
    if shutil.which("claude") is None:
        return emit(
            make_payload(
                ok=False,
                status="missing_cli",
                message="claude CLI not found on PATH.",
                suggested_exit_code=127,
            ),
            strict_exit=args.strict_exit,
        )
    try:
        process = subprocess.run(
            build_command(args),
            input=prompt,
            text=True,
            capture_output=True,
            check=False,
            timeout=args.timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = as_text(exc.stdout)
        stderr = as_text(exc.stderr)
        parsed, _ = parse_json_object(stdout) if stdout else (None, None)
        if parsed is not None:
            payload = payload_from_claude_json(
                parsed,
                status="timeout",
                message=f"Claude command timed out after {args.timeout_seconds:g} seconds.",
                ok=False,
                returncode=None,
                stdout=stdout,
                stderr=stderr,
                suggested_exit_code=124,
            )
        else:
            payload = make_payload(
                ok=False,
                status="timeout",
                message=f"Claude command timed out after {args.timeout_seconds:g} seconds.",
                returncode=None,
                stdout=stdout,
                stderr=stderr,
                suggested_exit_code=124,
            )
        return emit(payload, strict_exit=args.strict_exit)

    if process.returncode != 0:
        parsed, _ = parse_json_object(process.stdout) if process.stdout else (None, None)
        if parsed is not None:
            payload = payload_from_claude_json(
                parsed,
                status="command_failed",
                message=f"Claude exited with status {process.returncode}.",
                ok=False,
                returncode=process.returncode,
                stdout=process.stdout,
                stderr=process.stderr,
                suggested_exit_code=process.returncode,
            )
        else:
            payload = make_payload(
                ok=False,
                status="command_failed",
                message=f"Claude exited with status {process.returncode}.",
                returncode=process.returncode,
                stdout=process.stdout,
                stderr=process.stderr,
                suggested_exit_code=process.returncode,
            )
        return emit(payload, strict_exit=args.strict_exit)

    payload, parse_error = parse_json_object(process.stdout)
    if payload is None:
        return emit(
            make_payload(
                ok=False,
                status="invalid_json",
                message=f"Failed to parse Claude JSON: {parse_error}",
                returncode=process.returncode,
                stdout=process.stdout,
                stderr=process.stderr,
                suggested_exit_code=1,
            ),
            strict_exit=args.strict_exit,
        )

    return emit(
        payload_from_claude_json(
            payload,
            status="ok",
            message="Claude returned a usable result.",
            ok=True,
            returncode=process.returncode,
            stdout=None,
            stderr=None,
            suggested_exit_code=0,
        ),
        strict_exit=args.strict_exit,
    )


if __name__ == "__main__":
    raise SystemExit(main())
