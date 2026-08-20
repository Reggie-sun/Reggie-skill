#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import stat
import sys
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from cell_transport import (  # noqa: E402
    activity_sessions_from_output,
    cell_ids_from_output,
    session_sets_intersect,
    unique_uuid_prefix_replacements,
    wait_cell_id,
)
from session_signals import (  # noqa: E402
    DiagnosticSignal,
    analyze_signals,
    optimization_leads,
    stable_fingerprint,
)
from runner_command_shapes import (  # noqa: E402
    contains_dynamic_runner_command as _contains_dynamic_runner_command,
)


DEFAULT_SESSIONS_ROOT = Path("/home/reggie/.codex/sessions")
DEFAULT_OUTPUT_ROOT = Path("/home/reggie/.codex/session-diagnostics/minimax")
REPORT_SCHEMA_VERSION = 6
REPORT_MAX_BYTES = 2_000_000
REPORT_COMPLETE_MARKER = "<!-- capture-minimax-session:complete -->"
SESSION_ID_RE = re.compile(r"^[A-Za-z0-9-]{8,80}$")
ACTIVITY_RE = re.compile(
    r"\[sub-agent\]\s+activity\s+cli=minimax\s+elapsed=(\d+)s\s+"
    r"event=([^\s]+)(?:\s+session=([A-Za-z0-9._:-]+))?"
)
PROCESS_MARKER_RE = re.compile(r"^(?:SESSION_ID|session_id)=(\d+)$")
POLL_SESSION_RE = re.compile(r"session_id\s*:\s*(\d+)")
SECRET_PATTERNS = (
    re.compile(r"\bsk-(?:cp-)?[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{12,}"),
    re.compile(
        r"(?i)\b(?:api[_-]?key|token|secret|password)\s*[=:]\s*[^\s,;]+"
    ),
)
FAILURE_MARKERS = {
    "permission_or_grant": re.compile(
        r"(?i)permission denied|permission_denied|grant mismatch|not allowed"
    ),
    "timeout_or_stagnation": re.compile(
        r"(?i)timeout|timed out|stagnation|unresponsive"
    ),
    "protocol": re.compile(r"(?i)protocol_error|dialogue_protocol_error"),
    "evidence_incomplete": re.compile(r"(?i)evidence_incomplete"),
    "runner_validation": re.compile(r"(?i)runner_validation|definition-resolution"),
    "missing_terminal": re.compile(r"(?i)missing_terminal_result"),
}
TERMINATION_REASONS = frozenset(
    {
        "cli_exit",
        "dialogue_protocol_error",
        "evidence_incomplete",
        "idle_timeout",
        "missing_terminal_result",
        "output_limit",
        "permission_denied",
        "process_error",
        "runner_validation",
        "semantic_stagnation",
        "structured_output_retry_exhausted",
        "tool_error_loop",
        "transport_timeout",
    }
)
AGENT_STATUSES = frozenset(
    {"DONE", "DONE_WITH_CONCERNS", "NEEDS_CONTEXT", "BLOCKED", "PROTOCOL_ERROR"}
)
BLOCKER_KINDS = frozenset(
    {
        "grant_mismatch",
        "missing_required_evidence",
        "permission_denied",
        "tool_error_loop",
    }
)
CONCERN_CATEGORIES = frozenset(
    {
        "architecture_uncertainty",
        "compatibility_risk",
        "evidence_gap",
        "permission_or_tooling",
        "protocol_or_output",
        "test_gap",
        "timeout_or_performance",
    }
)
EVIDENCE_CATEGORIES = frozenset(
    {
        "commands_run",
        "files_inspected",
        "runtime_observed",
        "symbols_traced",
        "tests_inspected",
    }
)
RUNNER_PERMISSIONS = frozenset({"read-only", "safe-edit", "yolo"})
RUNNER_EFFORTS = frozenset({"default", "low", "medium", "high", "max"})
RUNNER_TOOLS_MODES = frozenset({"explicit", "default"})
MODEL_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,127}$")
TOOL_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:*+-]{0,79}$")


@dataclass
class Invocation:
    timestamp: str
    agent: str = "unknown"
    requested_cli: str = "definition/default"
    cwd: str = "unknown"
    dialogue: bool = False
    tdd: bool = False
    allow_path_count: int = 0
    allow_command_count: int = 0
    command_families: tuple[str, ...] = ()
    evidence_path_count: int = 0
    prompt_chars: int = 0
    prompt_sha256: str = "none"

    @property
    def retry_key(self) -> tuple[str, str, str]:
        return self.agent, self.cwd, self.prompt_sha256


@dataclass
class Terminal:
    timestamp: str
    status: str
    transport_exit_code: str
    cli_exit_code: str
    termination_reason: str
    agent_status: str
    evidence_count: int
    concern_count: int
    blocker_kind: str
    error_signature: str
    resolved_model: str = "unknown"
    resolved_effort: str = "unknown"
    resolved_permission: str = "unknown"
    resolved_tools_mode: str = "unknown"
    resolved_tools: tuple[str, ...] = ()
    concern_categories: tuple[str, ...] = ()
    evidence_categories: tuple[str, ...] = ()


@dataclass
class Activity:
    external_session: str
    elapsed_seconds: int
    event: str


@dataclass
class Capture:
    session_id: str
    source_path: Path
    source_cwd: str = "unknown"
    line_count: int = 0
    malformed_lines: int = 0
    unparsed_runner_calls: int = 0
    canonicalized_session_prefixes: int = 0
    invocations: list[Invocation] = field(default_factory=list)
    terminals: list[Terminal] = field(default_factory=list)
    activity_timeline: list[Activity] = field(default_factory=list)
    activities: dict[str, Counter[str]] = field(
        default_factory=lambda: defaultdict(Counter)
    )
    max_elapsed: dict[str, int] = field(default_factory=dict)
    failure_counts: Counter[str] = field(default_factory=Counter)


def _redact(value: str, limit: int = 240) -> str:
    redacted = value.replace("\x00", "")
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("<redacted>", redacted)
    redacted = " ".join(redacted.split())
    if len(redacted) > limit:
        redacted = redacted[: limit - 1] + "…"
    return redacted


def _markdown(value: object) -> str:
    return _redact(str(value)).replace("|", "\\|")


def _resolve_session(session_id: str, sessions_root: Path) -> Path:
    if not SESSION_ID_RE.fullmatch(session_id):
        raise ValueError("Session ID must contain only letters, digits, and hyphens.")
    if not sessions_root.is_dir():
        raise ValueError(f"Sessions root does not exist: {sessions_root}")
    matches = sorted(sessions_root.rglob(f"*{session_id}*.jsonl"))
    regular = [path for path in matches if path.is_file() and not path.is_symlink()]
    if not regular:
        raise ValueError(f"No rollout JSONL found for session {session_id}.")
    if len(regular) != 1:
        paths = ", ".join(str(path) for path in regular[:5])
        raise ValueError(f"Session {session_id} is ambiguous: {paths}")
    return regular[0]


def _text_values(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, child in value.items():
            if key in {"data", "blob", "image_url", "audio_url"}:
                continue
            yield from _text_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _text_values(child)


def _extract_cmd(raw_input: Any) -> str | None:
    if isinstance(raw_input, dict) and isinstance(raw_input.get("cmd"), str):
        return raw_input["cmd"]
    if not isinstance(raw_input, str):
        return None
    try:
        decoded = json.loads(raw_input)
    except json.JSONDecodeError:
        decoded = None
    if isinstance(decoded, dict) and isinstance(decoded.get("cmd"), str):
        return decoded["cmd"]
    match = re.search(
        r'(?:(?:"cmd")|(?:\bcmd))\s*:\s*("(?:\\.|[^"\\])*")',
        raw_input,
    )
    if match:
        try:
            command = json.loads(match.group(1))
        except json.JSONDecodeError:
            command = None
        if isinstance(command, str):
            return command
    stripped = raw_input.strip()
    if "run_subagent.py" in stripped and stripped.startswith(("python", "/")):
        return stripped
    return None


def _runner_args(command: str) -> list[str] | None:
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return None
    for index, token in enumerate(tokens[:-1]):
        if Path(token).name.startswith("python") and Path(tokens[index + 1]).name == "run_subagent.py":
            return tokens[index + 2 :]
    return None


def _flag_values(args: list[str], flag: str) -> list[str]:
    values: list[str] = []
    for index, token in enumerate(args):
        if token == flag and index + 1 < len(args):
            values.append(args[index + 1])
        elif token.startswith(flag + "="):
            values.append(token.split("=", 1)[1])
    return values


def _command_family(command: str) -> str:
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return "unparseable"
    if not tokens:
        return "empty"
    index = 0
    while index < len(tokens) and "=" in tokens[index] and not tokens[index].startswith("-"):
        index += 1
    return Path(tokens[index]).name if index < len(tokens) else "environment-only"


def _parse_invocation(timestamp: str, raw_input: Any) -> Invocation | None:
    command = _extract_cmd(raw_input)
    if command is None:
        return None
    args = _runner_args(command)
    if args is None:
        return None
    agent_values = _flag_values(args, "--agent")
    cwd_values = _flag_values(args, "--cwd")
    cli_values = _flag_values(args, "--cli")
    prompts = _flag_values(args, "--prompt")
    if "--list" in args or not agent_values or not cwd_values or not prompts:
        return None
    prompt = prompts[-1] if prompts else ""
    commands = _flag_values(args, "--allow-command")
    agent = agent_values[-1] if agent_values else "unknown"
    if "/" in agent:
        agent = Path(agent).stem
    return Invocation(
        timestamp=timestamp,
        agent=_redact(agent, 80),
        requested_cli=_redact(cli_values[-1], 40) if cli_values else "definition/default",
        cwd=_redact(cwd_values[-1], 180) if cwd_values else "unknown",
        dialogue="--dialogue" in args,
        tdd="--tdd" in args,
        allow_path_count=len(_flag_values(args, "--allow-path")),
        allow_command_count=len(commands),
        command_families=tuple(sorted({_command_family(item) for item in commands})),
        evidence_path_count=len(_flag_values(args, "--require-evidence-path")),
        prompt_chars=len(prompt),
        prompt_sha256=hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]
        if prompt
        else "none",
    )


def _decode_json_dict(value: str) -> dict[str, Any] | None:
    stripped = value.strip()
    if not stripped:
        return None
    try:
        decoded = json.loads(stripped)
    except json.JSONDecodeError:
        if not stripped.startswith(r"{\""):
            return None
        try:
            decoded = json.loads(json.loads('"' + stripped + '"'))
        except (json.JSONDecodeError, TypeError):
            return None
    return decoded if isinstance(decoded, dict) else None


def _is_terminal_envelope(value: dict[str, Any]) -> bool:
    if value.get("cli") != "minimax":
        return False
    if value.get("status") not in {"success", "error", "partial"}:
        return False
    if not isinstance(value.get("exit_code"), int):
        return False
    if not isinstance(value.get("transport_exit_code"), int):
        return False
    if value.get("cli_exit_code") is not None and not isinstance(
        value.get("cli_exit_code"), int
    ):
        return False
    if not isinstance(value.get("termination_reason"), str):
        return False
    if "agent_status" in value and not isinstance(value.get("agent_status"), str):
        return False
    return True


def _is_exec_wrapper(value: dict[str, Any]) -> bool:
    if not isinstance(value.get("output"), (dict, list, str)):
        return False
    if not isinstance(value.get("wall_time_seconds"), (int, float)):
        return False
    exit_code = value.get("exit_code")
    process_id = value.get("session_id")
    valid_exit = isinstance(exit_code, int)
    valid_process = isinstance(process_id, int) or (
        isinstance(process_id, str) and process_id.isdigit()
    )
    return valid_exit or valid_process


def _transport_wrappers_from_output(output: Any) -> Iterable[dict[str, Any]]:
    if isinstance(output, list):
        for item in output:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                yield from _transport_wrappers_from_output(item["text"])
            elif isinstance(item, (dict, list, str)):
                yield from _transport_wrappers_from_output(item)
        return
    if isinstance(output, dict):
        if _is_exec_wrapper(output):
            yield output
        return
    if not isinstance(output, str):
        return
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    candidates = (output, lines[-1] if lines else "")
    for candidate_text in candidates:
        candidate = _decode_json_dict(candidate_text)
        if candidate is not None and _is_exec_wrapper(candidate):
            yield candidate
            return


def _terminal_dicts_from_output(output: Any) -> Iterable[dict[str, Any]]:
    for wrapper in _transport_wrappers_from_output(output):
        runner_output = wrapper["output"]
        if not isinstance(runner_output, str):
            continue
        lines = [line.strip() for line in runner_output.splitlines() if line.strip()]
        if not lines:
            continue
        if any(
            ACTIVITY_RE.fullmatch(line) is None
            and PROCESS_MARKER_RE.fullmatch(line) is None
            for line in lines[:-1]
        ):
            continue
        candidate = _decode_json_dict(lines[-1])
        if candidate is not None and _is_terminal_envelope(candidate):
            yield candidate


def _terminal_dicts_from_selected_output(
    output: Any,
) -> Iterable[dict[str, Any]]:
    """Decode terminal truth from an already-associated runner or poll output."""
    yield from _terminal_dicts_from_output(output)
    for text in _text_values(output):
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            continue
        candidate = _decode_json_dict(lines[-1])
        if candidate is None or not _is_terminal_envelope(candidate):
            continue
        if any(
            ACTIVITY_RE.fullmatch(line) is None
            and PROCESS_MARKER_RE.fullmatch(line) is None
            for line in lines[:-1]
        ):
            continue
        yield candidate


def _process_ids_from_output(output: Any) -> set[str]:
    process_ids: set[str] = set()
    for wrapper in _transport_wrappers_from_output(output):
        value = wrapper.get("session_id")
        if isinstance(value, int) or (isinstance(value, str) and value.isdigit()):
            process_ids.add(str(value))
    for text in _text_values(output):
        for line in text.splitlines():
            match = PROCESS_MARKER_RE.fullmatch(line.strip())
            if match:
                process_ids.add(match.group(1))
    return process_ids


def _has_runner_framing(output: Any) -> bool:
    for wrapper in _transport_wrappers_from_output(output):
        runner_output = wrapper.get("output")
        if not isinstance(runner_output, str):
            continue
        for line in runner_output.splitlines():
            stripped = line.strip()
            if ACTIVITY_RE.fullmatch(stripped) or PROCESS_MARKER_RE.fullmatch(stripped):
                return True
    for text in _text_values(output):
        for line in text.splitlines():
            stripped = line.strip()
            if ACTIVITY_RE.fullmatch(stripped) or PROCESS_MARKER_RE.fullmatch(stripped):
                return True
    return False


def _categorical(value: object, allowed: frozenset[str]) -> str:
    if not isinstance(value, str) or not value:
        return "unknown"
    return value if value in allowed else "other"


def _category_tuple(value: object, allowed: frozenset[str]) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    categories = {
        item if item in allowed else "other"
        for item in value
        if isinstance(item, str)
    }
    return tuple(sorted(categories))


def _runner_tools(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > 32:
        return ()
    tools = [item for item in value if isinstance(item, str) and TOOL_NAME_RE.fullmatch(item)]
    return tuple(tools) if len(tools) == len(value) else ()


def _terminal_from_dict(timestamp: str, value: dict[str, Any]) -> Terminal | None:
    if not _is_terminal_envelope(value):
        return None
    blocker = value.get("blocker")
    raw_blocker_kind = blocker.get("kind") if isinstance(blocker, dict) else None
    blocker_kind = (
        _categorical(raw_blocker_kind, BLOCKER_KINDS)
        if raw_blocker_kind is not None
        else "none"
    )
    observed = value.get("observed_evidence_paths")
    concerns = value.get("concerns")
    runner_context = value.get("runner_context")
    if not isinstance(runner_context, dict):
        runner_context = {}
    raw_model = runner_context.get("model")
    if not isinstance(raw_model, str) or not raw_model:
        resolved_model = "unknown"
    elif MODEL_IDENTIFIER_RE.fullmatch(raw_model):
        resolved_model = raw_model
    else:
        resolved_model = "other"
    error = value.get("error", "")
    category_text = " ".join(
        str(item)
        for item in (
            value.get("status", ""),
            _categorical(value.get("termination_reason"), TERMINATION_REASONS),
            _categorical(value.get("agent_status"), AGENT_STATUSES),
            blocker_kind,
            error if isinstance(error, str) else "",
        )
    )
    categories = tuple(
        name for name, pattern in FAILURE_MARKERS.items() if pattern.search(category_text)
    )
    error_signature = ",".join(categories)
    if not error_signature and isinstance(error, str) and error:
        error_signature = "unclassified_error"
    if not error_signature:
        error_signature = "none"
    return Terminal(
        timestamp=timestamp,
        status=str(value.get("status", "unknown")),
        transport_exit_code=str(value.get("transport_exit_code", "unknown")),
        cli_exit_code=str(value.get("cli_exit_code", "unknown")),
        termination_reason=_categorical(
            value.get("termination_reason"), TERMINATION_REASONS
        ),
        agent_status=_categorical(value.get("agent_status"), AGENT_STATUSES),
        evidence_count=len(observed) if isinstance(observed, list) else 0,
        concern_count=len(concerns) if isinstance(concerns, list) else 0,
        blocker_kind=_redact(str(blocker_kind), 80),
        error_signature=error_signature,
        resolved_model=resolved_model,
        resolved_effort=_categorical(runner_context.get("effort"), RUNNER_EFFORTS),
        resolved_permission=_categorical(
            runner_context.get("permission"), RUNNER_PERMISSIONS
        ),
        resolved_tools_mode=_categorical(
            runner_context.get("tools_mode"), RUNNER_TOOLS_MODES
        ),
        resolved_tools=_runner_tools(runner_context.get("tools")),
        concern_categories=_category_tuple(
            value.get("concern_categories"), CONCERN_CATEGORIES
        ),
        evidence_categories=_category_tuple(
            value.get("evidence_categories"), EVIDENCE_CATEGORIES
        ),
    )


def _terminal_key(terminal: Terminal) -> tuple[object, ...]:
    return (
        terminal.timestamp,
        terminal.status,
        terminal.transport_exit_code,
        terminal.cli_exit_code,
        terminal.termination_reason,
        terminal.agent_status,
        terminal.evidence_count,
        terminal.concern_count,
        terminal.blocker_kind,
        terminal.error_signature,
        terminal.resolved_model,
        terminal.resolved_effort,
        terminal.resolved_permission,
        terminal.resolved_tools_mode,
        terminal.resolved_tools,
        terminal.concern_categories,
        terminal.evidence_categories,
    )


def _record_failure_markers(capture: Capture, text: str) -> None:
    safe_text = _redact(text, 20_000)
    for name, pattern in FAILURE_MARKERS.items():
        if pattern.search(safe_text):
            capture.failure_counts[name] += 1


def _canonicalize_activity_sessions(capture: Capture) -> None:
    replacements = unique_uuid_prefix_replacements(
        item.external_session for item in capture.activity_timeline
    )
    if not replacements:
        return

    capture.canonicalized_session_prefixes = len(replacements)
    capture.activities = defaultdict(Counter)
    capture.max_elapsed = {}
    for item in capture.activity_timeline:
        item.external_session = replacements.get(
            item.external_session, item.external_session
        )
        capture.activities[item.external_session][item.event] += 1
        capture.max_elapsed[item.external_session] = max(
            capture.max_elapsed.get(item.external_session, 0),
            item.elapsed_seconds,
        )


def capture_session(session_id: str, source_path: Path) -> Capture:
    capture = Capture(session_id=session_id, source_path=source_path)
    terminal_seen: set[tuple[object, ...]] = set()
    records: list[dict[str, Any]] = []
    source_session_ids: set[str] = set()

    with source_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            capture.line_count += 1
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                capture.malformed_lines += 1
                continue
            if isinstance(record, dict):
                records.append(record)
                if record.get("type") == "session_meta":
                    payload = record.get("payload")
                    if isinstance(payload, dict) and isinstance(payload.get("id"), str):
                        source_session_ids.add(payload["id"])

    if not source_session_ids:
        raise ValueError("Session file has no session_meta identity.")
    if source_session_ids != {session_id}:
        raise ValueError(
            f"Session file identities {sorted(source_session_ids)!r} do not match "
            f"the single requested session {session_id!r}."
        )

    outputs_by_call: dict[str, tuple[str, Any]] = {}
    output_indices_by_call: dict[str, int] = {}
    function_outputs_by_call: dict[str, tuple[str, Any]] = {}
    function_output_indices_by_call: dict[str, int] = {}
    wait_calls_by_cell: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for record_index, record in enumerate(records):
        payload = record.get("payload")
        if (
            record.get("type") == "response_item"
            and isinstance(payload, dict)
            and payload.get("type") == "custom_tool_call_output"
            and isinstance(payload.get("call_id"), str)
        ):
            outputs_by_call[payload["call_id"]] = (
                str(record.get("timestamp", "unknown")),
                payload.get("output"),
            )
            output_indices_by_call[payload["call_id"]] = record_index
        elif (
            record.get("type") == "response_item"
            and isinstance(payload, dict)
            and payload.get("type") == "function_call_output"
            and isinstance(payload.get("call_id"), str)
        ):
            function_outputs_by_call[payload["call_id"]] = (
                str(record.get("timestamp", "unknown")),
                payload.get("output"),
            )
            function_output_indices_by_call[payload["call_id"]] = record_index
        elif record.get("type") == "response_item" and isinstance(payload, dict):
            cell_id = wait_cell_id(payload)
            call_id = payload.get("call_id")
            if cell_id is not None and isinstance(call_id, str):
                wait_calls_by_cell[cell_id].append((call_id, record_index))

    selected_call_ids: set[str] = set()
    selected_function_call_ids: set[str] = set()
    process_ids: set[str] = set()
    runner_external_sessions: set[str] = set()

    def attached_wait_call_ids(output: Any, source_index: int) -> set[str]:
        attached: set[str] = set()
        for cell_id in cell_ids_from_output(output):
            wait_calls = wait_calls_by_cell.get(cell_id, ())
            if len(wait_calls) != 1:
                continue
            wait_call_id, wait_index = wait_calls[0]
            output_index = function_output_indices_by_call.get(wait_call_id)
            if output_index is None or not source_index < wait_index < output_index:
                continue
            attached.add(wait_call_id)
        return attached

    def attach_wait_outputs(output: Any, source_index: int) -> None:
        for wait_call_id in attached_wait_call_ids(output, source_index):
            output_record = function_outputs_by_call[wait_call_id]
            selected_function_call_ids.add(wait_call_id)
            process_ids.update(_process_ids_from_output(output_record[1]))
            runner_external_sessions.update(
                activity_sessions_from_output(output_record[1], ACTIVITY_RE)
            )

    def candidate_wait_sessions(output: Any, source_index: int) -> set[str]:
        return {
            session
            for wait_call_id in attached_wait_call_ids(output, source_index)
            for session in activity_sessions_from_output(
                function_outputs_by_call[wait_call_id][1], ACTIVITY_RE
            )
        }

    for record in records:
        payload = record.get("payload")
        if not (
            record.get("type") == "response_item"
            and isinstance(payload, dict)
            and payload.get("type") == "custom_tool_call"
            and payload.get("name") == "exec"
        ):
            continue
        invocation = _parse_invocation(
            str(record.get("timestamp", "unknown")), payload.get("input")
        )
        if invocation is None:
            call_id = payload.get("call_id")
            output_record = (
                outputs_by_call.get(call_id) if isinstance(call_id, str) else None
            )
            if (
                isinstance(call_id, str)
                and _contains_dynamic_runner_command(payload.get("input"))
                and output_record is not None
                and _has_runner_framing(output_record[1])
            ):
                capture.unparsed_runner_calls += 1
                selected_call_ids.add(call_id)
                process_ids.update(_process_ids_from_output(output_record[1]))
                runner_external_sessions.update(
                    activity_sessions_from_output(output_record[1], ACTIVITY_RE)
                )
                attach_wait_outputs(output_record[1], output_indices_by_call[call_id])
            continue
        capture.invocations.append(invocation)
        call_id = payload.get("call_id")
        if isinstance(call_id, str):
            selected_call_ids.add(call_id)
            output_record = outputs_by_call.get(call_id)
            if output_record is not None:
                process_ids.update(_process_ids_from_output(output_record[1]))
                runner_external_sessions.update(
                    activity_sessions_from_output(output_record[1], ACTIVITY_RE)
                )
                attach_wait_outputs(output_record[1], output_indices_by_call[call_id])

    poll_session_universe = set(runner_external_sessions)
    for record in records:
        payload = record.get("payload")
        if not (
            record.get("type") == "response_item"
            and isinstance(payload, dict)
            and payload.get("type") == "custom_tool_call"
            and payload.get("name") == "exec"
            and isinstance(payload.get("input"), str)
            and "tools.write_stdin" in payload["input"]
            and isinstance(payload.get("call_id"), str)
        ):
            continue
        call_id = payload["call_id"]
        output_record = outputs_by_call.get(call_id)
        if output_record is None:
            continue
        poll_session_universe.update(
            candidate_wait_sessions(
                output_record[1], output_indices_by_call[call_id]
            )
        )

    changed = True
    while changed:
        changed = False
        for record in records:
            payload = record.get("payload")
            if not (
                record.get("type") == "response_item"
                and isinstance(payload, dict)
                and payload.get("type") == "custom_tool_call"
                and payload.get("name") == "exec"
                and isinstance(payload.get("input"), str)
                and "tools.write_stdin" in payload["input"]
            ):
                continue
            call_id = payload.get("call_id")
            if not isinstance(call_id, str) or call_id in selected_call_ids:
                continue
            output_record = outputs_by_call.get(call_id)
            if output_record is None:
                continue
            poll_ids = set(POLL_SESSION_RE.findall(payload["input"]))
            candidate_sessions = candidate_wait_sessions(
                output_record[1], output_indices_by_call[call_id]
            )
            if not (
                poll_ids.intersection(process_ids)
                or session_sets_intersect(
                    candidate_sessions,
                    runner_external_sessions,
                    poll_session_universe,
                )
            ):
                continue
            selected_call_ids.add(call_id)
            changed = True
            process_ids.update(_process_ids_from_output(output_record[1]))
            runner_external_sessions.update(
                activity_sessions_from_output(output_record[1], ACTIVITY_RE)
            )
            attach_wait_outputs(output_record[1], output_indices_by_call[call_id])

    for record in records:
        timestamp = str(record.get("timestamp", "unknown"))
        if record.get("type") == "session_meta":
            payload = record.get("payload")
            if isinstance(payload, dict):
                capture.source_cwd = _redact(str(payload.get("cwd", "unknown")), 180)
        payload = record.get("payload")
        if not (record.get("type") == "response_item" and isinstance(payload, dict)):
            continue
        is_selected_custom = (
            payload.get("type") == "custom_tool_call_output"
            and payload.get("call_id") in selected_call_ids
        )
        is_selected_function = (
            payload.get("type") == "function_call_output"
            and payload.get("call_id") in selected_function_call_ids
        )
        if not (is_selected_custom or is_selected_function):
            continue
        output = payload.get("output")
        for text in _text_values(output):
            for match in ACTIVITY_RE.finditer(text):
                elapsed = int(match.group(1))
                event = _redact(match.group(2), 80)
                external_session = _redact(match.group(3) or "unknown", 100)
                capture.activities[external_session][event] += 1
                capture.activity_timeline.append(
                    Activity(
                        external_session=external_session,
                        elapsed_seconds=elapsed,
                        event=event,
                    )
                )
                capture.max_elapsed[external_session] = max(
                    capture.max_elapsed.get(external_session, 0), elapsed
                )
        for decoded in _terminal_dicts_from_selected_output(output):
            terminal = _terminal_from_dict(timestamp, decoded)
            if terminal is None:
                continue
            key = _terminal_key(terminal)
            if key not in terminal_seen:
                terminal_seen.add(key)
                capture.terminals.append(terminal)
                _record_failure_markers(
                    capture,
                    " ".join(
                        (
                            terminal.status,
                            terminal.termination_reason,
                            terminal.agent_status,
                            terminal.blocker_kind,
                            terminal.error_signature,
                        )
                    ),
                )
    _canonicalize_activity_sessions(capture)
    return capture


def _optimization_leads(capture: Capture) -> list[str]:
    leads: list[str] = []
    marker_to_lead = {
        "permission_or_grant": "Inspect exact command/path grants and denial classification.",
        "timeout_or_stagnation": "Inspect semantic-progress, heartbeat, and wall-clock termination behavior.",
        "protocol": "Inspect dialogue schema normalization and terminal-envelope handling.",
        "evidence_incomplete": "Inspect required-evidence selection and successful tool-result accounting.",
        "runner_validation": "Inspect definition resolution and pre-backend invocation validation.",
        "missing_terminal": "Inspect attached-process polling and clean terminal-result promotion.",
    }
    for marker, lead in marker_to_lead.items():
        if capture.failure_counts.get(marker):
            leads.append(lead)
    retry_counts = Counter(item.retry_key for item in capture.invocations)
    if any(count > 1 for count in retry_counts.values()):
        leads.append("Compare repeated prompt hashes against the bounded fresh-retry policy.")
    if capture.unparsed_runner_calls:
        leads.append(
            "Runner activity was captured from a dynamic command shape; use literal "
            "runner flags when complete invocation-shape diagnostics are required."
        )
    if not capture.terminals and (
        capture.invocations or capture.unparsed_runner_calls
    ):
        leads.append("No MiniMax terminal record was captured; inspect process attachment and output routing.")
    leads.extend(optimization_leads(_diagnostic_signals(capture)))
    if not leads:
        leads.append("No known runner failure signature was detected; inspect efficiency and evidence quality manually.")
    return leads


def _diagnostic_signals(capture: Capture) -> tuple[DiagnosticSignal, ...]:
    signals = list(
        analyze_signals(
            ((item.agent, item.dialogue) for item in capture.invocations),
            tuple(
                (item.external_session, item.elapsed_seconds, item.event)
                for item in capture.activity_timeline
            ),
            tuple(
                (item.agent_status, item.evidence_count, item.concern_count)
                for item in capture.terminals
            ),
        )
    )
    if capture.canonicalized_session_prefixes:
        signals.append(
            DiagnosticSignal(
                "external_session_prefix_canonicalized",
                capture.canonicalized_session_prefixes,
                "unique truncated UUID prefixes merged",
            )
        )
    return tuple(signals)


def _capture_fingerprint(capture: Capture) -> str:
    return stable_fingerprint(
        {
            "session_id": capture.session_id,
            "report_schema_version": REPORT_SCHEMA_VERSION,
            "unparsed_runner_calls": capture.unparsed_runner_calls,
            "canonicalized_session_prefixes": capture.canonicalized_session_prefixes,
            "invocations": [item.__dict__ for item in capture.invocations],
            "terminals": [item.__dict__ for item in capture.terminals],
            "activities": [item.__dict__ for item in capture.activity_timeline],
            "failure_counts": dict(sorted(capture.failure_counts.items())),
        }
    )


def _existing_report(
    output_root: Path, session_id: str, fingerprint: str
) -> Path | None:
    marker = f"- Capture fingerprint: `{fingerprint}`"
    required_lines = {
        "# MiniMax Subagent Session Capture",
        f"- Session ID: `{session_id}`",
        f"- Report schema version: `{REPORT_SCHEMA_VERSION}`",
        marker,
    }
    if not output_root.is_dir():
        return None
    for candidate in sorted(output_root.glob(f"{session_id}-*.md"), reverse=True):
        descriptor: int | None = None
        try:
            flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(candidate, flags)
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode):
                continue
            if stat.S_IMODE(before.st_mode) != 0o600:
                continue
            if before.st_size > REPORT_MAX_BYTES:
                continue
            chunks: list[bytes] = []
            total = 0
            while total <= REPORT_MAX_BYTES:
                chunk = os.read(
                    descriptor,
                    min(65_536, REPORT_MAX_BYTES + 1 - total),
                )
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
            after = os.fstat(descriptor)
            if total > REPORT_MAX_BYTES or after.st_size != before.st_size:
                continue
            content = b"".join(chunks).decode("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        finally:
            if descriptor is not None:
                os.close(descriptor)
        lines = set(content.splitlines())
        if required_lines.issubset(lines) and content.endswith(
            REPORT_COMPLETE_MARKER + "\n"
        ):
            return candidate
    return None


def render_markdown(capture: Capture, captured_at: str) -> str:
    fingerprint = _capture_fingerprint(capture)
    diagnostic_signals = _diagnostic_signals(capture)
    lines = [
        "# MiniMax Subagent Session Capture",
        "",
        "## Metadata",
        "",
        f"- Session ID: `{_markdown(capture.session_id)}`",
        f"- Source rollout: `{_markdown(capture.source_path)}`",
        f"- Source cwd: `{_markdown(capture.source_cwd)}`",
        f"- Captured at: `{_markdown(captured_at)}`",
        f"- Capture fingerprint: `{fingerprint}`",
        f"- Report schema version: `{REPORT_SCHEMA_VERSION}`",
        f"- JSONL lines: `{capture.line_count}`",
        f"- Malformed lines skipped: `{capture.malformed_lines}`",
        "",
        "## Invocation Shape",
        "",
    ]
    if capture.invocations:
        lines.extend(
            [
                "| # | Timestamp | Agent | Requested CLI | cwd | Dialogue | TDD | Paths | Commands | Command families | Evidence paths | Prompt chars | Prompt hash |",
                "|---:|---|---|---|---|---:|---:|---:|---:|---|---:|---:|---|",
            ]
        )
        for index, item in enumerate(capture.invocations, 1):
            families = ", ".join(item.command_families) or "none"
            lines.append(
                f"| {index} | {_markdown(item.timestamp)} | {_markdown(item.agent)} | "
                f"{_markdown(item.requested_cli)} | {_markdown(item.cwd)} | "
                f"{str(item.dialogue).lower()} | {str(item.tdd).lower()} | "
                f"{item.allow_path_count} | {item.allow_command_count} | "
                f"{_markdown(families)} | {item.evidence_path_count} | "
                f"{item.prompt_chars} | `{item.prompt_sha256}` |"
            )
        if capture.unparsed_runner_calls:
            lines.append("")
            lines.append(
                f"{capture.unparsed_runner_calls} runner call(s) used a dynamic command "
                "shape; activity and terminal truth were associated without inventing "
                "invocation fields."
            )
    elif capture.unparsed_runner_calls:
        lines.append(
            f"{capture.unparsed_runner_calls} runner call(s) used a dynamic command "
            "shape; activity and terminal truth were associated without inventing "
            "invocation fields."
        )
    else:
        lines.append("No `run_subagent.py` invocation was detected.")

    lines.extend(["", "## MiniMax Activity", ""])
    if capture.activities:
        lines.extend(
            [
                "| External session | Max elapsed seconds | Event counts |",
                "|---|---:|---|",
            ]
        )
        for session, events in sorted(capture.activities.items()):
            event_text = ", ".join(f"{name}={count}" for name, count in sorted(events.items()))
            lines.append(
                f"| `{_markdown(session)}` | {capture.max_elapsed.get(session, 0)} | {_markdown(event_text)} |"
            )
    else:
        lines.append("No MiniMax activity heartbeat was detected.")

    lines.extend(["", "## Action Timeline", ""])
    if capture.activity_timeline:
        lines.extend(
            [
                "| # | External session | Elapsed seconds | Event |",
                "|---:|---|---:|---|",
            ]
        )
        for index, item in enumerate(capture.activity_timeline, 1):
            lines.append(
                f"| {index} | `{_markdown(item.external_session)}` | "
                f"{item.elapsed_seconds} | {_markdown(item.event)} |"
            )
    else:
        lines.append("No external MiniMax action was detected.")

    lines.extend(["", "## Terminal Truth", ""])
    if capture.terminals:
        lines.extend(
            [
                "| # | Timestamp | status | transport | CLI | reason | agent_status | Model | Effort | Permission | Tools | Evidence | Evidence categories | Concerns | Concern categories | Blocker | Error signature |",
                "|---:|---|---|---|---|---|---|---|---|---|---|---:|---|---:|---|---|---|",
            ]
        )
        for index, item in enumerate(capture.terminals, 1):
            tools_text = (
                ", ".join(item.resolved_tools) or "none"
                if item.resolved_tools_mode == "explicit"
                else item.resolved_tools_mode
            )
            lines.append(
                f"| {index} | {_markdown(item.timestamp)} | {_markdown(item.status)} | "
                f"{_markdown(item.transport_exit_code)} | {_markdown(item.cli_exit_code)} | "
                f"{_markdown(item.termination_reason)} | {_markdown(item.agent_status)} | "
                f"{_markdown(item.resolved_model)} | {_markdown(item.resolved_effort)} | "
                f"{_markdown(item.resolved_permission)} | "
                f"{_markdown(tools_text)} | "
                f"{item.evidence_count} | "
                f"{_markdown(', '.join(item.evidence_categories) or 'none')} | "
                f"{item.concern_count} | "
                f"{_markdown(', '.join(item.concern_categories) or 'none')} | "
                f"{_markdown(item.blocker_kind)} | "
                f"{_markdown(item.error_signature)} |"
            )
    else:
        lines.append("No structured MiniMax terminal result was detected.")

    lines.extend(["", "## Failure Signatures", ""])
    if capture.failure_counts:
        for name, count in sorted(capture.failure_counts.items()):
            lines.append(f"- `{_markdown(name)}`: {count} matching record(s)")
    else:
        lines.append("- No known failure marker detected.")

    lines.extend(["", "## Diagnostic Signals", ""])
    if diagnostic_signals:
        lines.extend(
            [
                "| Signal | Count | Detail |",
                "|---|---:|---|",
            ]
        )
        for signal in diagnostic_signals:
            lines.append(
                f"| `{_markdown(signal.name)}` | {signal.count} | "
                f"{_markdown(signal.detail)} |"
            )
    else:
        lines.append("- No activity-level diagnostic signal detected.")

    lines.extend(["", "## Optimization Leads", ""])
    lines.extend(f"- {lead}" for lead in _optimization_leads(capture))
    lines.extend(
        [
            "",
            "## Sanitization And Evidence Limits",
            "",
            "- Raw prompts and exact commands are omitted; prompt hashes are truncated SHA-256 identifiers.",
            "- Command grants expose only executable families and counts.",
            "- Provider result prose, tool payloads, environment values, and credentials are not copied.",
            "- Invocation and activity records do not prove task correctness.",
            "- Re-open the source rollout only with narrow, redacted queries for a specific hypothesis.",
            "",
            REPORT_COMPLETE_MARKER,
            "",
        ]
    )
    return "\n".join(lines)


def _default_output(session_id: str, fingerprint: str, output_root: Path) -> Path:
    return output_root / f"{session_id}-{fingerprint}.md"


def _write_report(output: Path, content: str, force: bool) -> None:
    encoded = content.encode("utf-8")
    if len(encoded) > REPORT_MAX_BYTES:
        raise ValueError(
            f"Report exceeds the {REPORT_MAX_BYTES}-byte limit."
        )
    descriptor, temporary_name = tempfile.mkstemp(
        dir=output.parent,
        prefix=f".{output.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        if force:
            os.replace(temporary, output)
        else:
            os.link(temporary, output, follow_symlinks=False)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture sanitized MiniMax subagent activity from a Codex rollout."
    )
    parser.add_argument("--session-id", default=os.environ.get("CODEX_THREAD_ID"))
    parser.add_argument("--session-file", type=Path)
    parser.add_argument("--sessions-root", type=Path, default=DEFAULT_SESSIONS_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    if not args.session_id:
        print("error: provide --session-id or set CODEX_THREAD_ID", file=sys.stderr)
        return 2
    try:
        source = args.session_file or _resolve_session(args.session_id, args.sessions_root)
        if not source.is_file() or source.is_symlink():
            raise ValueError(f"Session file must be a regular non-symlink file: {source}")
        captured_at_dt = datetime.now(timezone.utc)
        capture = capture_session(args.session_id, source)
        if args.output is None:
            existing = _existing_report(
                args.output_root,
                args.session_id,
                _capture_fingerprint(capture),
            )
            if existing is not None:
                print(existing)
                return 0
        fingerprint = _capture_fingerprint(capture)
        output = args.output or _default_output(
            args.session_id,
            fingerprint,
            args.output_root,
        )
        if output.is_symlink():
            raise ValueError(f"Output path must not be a symlink: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            _write_report(
                output,
                render_markdown(capture, captured_at_dt.isoformat()),
                force=args.force,
            )
        except FileExistsError:
            if args.output is not None:
                raise
            winner = _existing_report(args.output_root, args.session_id, fingerprint)
            if winner is None:
                raise
            output = winner
    except (OSError, ValueError) as exc:
        print(f"error: {_redact(str(exc), 400)}", file=sys.stderr)
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
