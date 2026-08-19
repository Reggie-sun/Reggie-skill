from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


_MAX_ANSWER_FILE_BYTES = 64 * 1024
_VALID_AGENT_STATUSES = frozenset(
    {"DONE", "DONE_WITH_CONCERNS", "NEEDS_CONTEXT", "BLOCKED"}
)
_ENVELOPE_PATTERN = re.compile(
    r"<subagent_result>\s*(.*?)\s*</subagent_result>",
    re.DOTALL,
)
_DIALOGUE_FIELDS = frozenset(
    {"status", "summary", "result", "questions", "state_file", "concerns"}
)
_DIALOGUE_OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "status": {"type": "string", "enum": sorted(_VALID_AGENT_STATUSES)},
        "summary": {"type": "string", "minLength": 1},
        "result": {"type": "string", "minLength": 1},
        "questions": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "maxItems": 3,
        },
        "state_file": {
            "anyOf": [
                {"type": "string", "minLength": 1},
                {"type": "null"},
            ]
        },
        "concerns": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
        },
    },
    "required": sorted(_DIALOGUE_FIELDS),
}

_PROTOCOL_CONTEXT = """## Bounded Dialogue Protocol

This is a fresh, non-interactive invocation. Do not wait for live input and do
not use session persistence. If a material decision or missing fact prevents
safe progress, stop before guessing or editing source files and return
`NEEDS_CONTEXT` with one to three precise questions. The parent will answer in
an artifact and start a fresh invocation with the same task and current state.

End every final response with exactly one JSON envelope after any concise
human-readable report:

<subagent_result>{"status":"DONE|DONE_WITH_CONCERNS|NEEDS_CONTEXT|BLOCKED","summary":"one-line outcome","questions":[],"state_file":null,"concerns":[]}</subagent_result>

Rules:
- `NEEDS_CONTEXT` requires one to three non-empty questions.
- `DONE_WITH_CONCERNS` requires at least one concern.
- `concerns` must be empty unless status is `DONE_WITH_CONCERNS`.
- `questions` must be empty unless status is `NEEDS_CONTEXT`.
- The summary, result, and concerns must agree. A material unresolved concern
  must remain qualified in the conclusion; do not present it as confirmed.
- `state_file` must be `null` unless useful state was written; a non-null value
  must name an existing regular file inside the working directory.
- Do not include a second envelope or any content after the closing tag.
"""

_STRUCTURED_PROTOCOL_CONTEXT = """## Bounded Dialogue Protocol

This is a fresh, non-interactive invocation. Do not wait for live input and do
not use session persistence. The transport requires structured output. Put the
complete human-readable findings or implementation report in `result`, then
provide `status`, `summary`, `questions`, `state_file`, and `concerns` exactly
as required by the supplied JSON schema. Do not print an XML envelope or place
any report outside the structured output.

Rules:
- `NEEDS_CONTEXT` requires one to three non-empty questions.
- `DONE_WITH_CONCERNS` requires at least one concern.
- `concerns` must be empty unless status is `DONE_WITH_CONCERNS`.
- `questions` must be empty unless status is `NEEDS_CONTEXT`.
- The summary, result, and concerns must agree. A material unresolved concern
  must remain qualified in the conclusion; do not present it as confirmed.
- `state_file` must be `null` unless useful state was written; a non-null value
  must name an existing regular file inside the working directory.
"""


def dialogue_json_schema() -> str:
    """Return the stable Claude CLI schema for bounded dialogue results."""
    return json.dumps(
        _DIALOGUE_OUTPUT_SCHEMA,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _protocol_error(result: dict, message: str) -> dict:
    return {
        **result,
        "status": "error",
        "exit_code": 2,
        "transport_exit_code": 1,
        "agent_status": "PROTOCOL_ERROR",
        "termination_reason": "dialogue_protocol_error",
        "error": f"Bounded dialogue protocol error: {message}",
    }


def _resolve_regular_file(path_value: str, cwd: str, label: str) -> tuple[Path, str]:
    if path_value.startswith("~"):
        raise ValueError(f"{label} must not use home-directory expansion.")
    if any(ord(character) < 32 for character in path_value):
        raise ValueError(f"{label} contains a control character.")
    root = Path(cwd).resolve()
    supplied = Path(path_value)
    candidate = supplied if supplied.is_absolute() else root / supplied

    if candidate.is_symlink():
        raise ValueError(f"{label} {path_value!r} must not be a symlink.")

    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"{label} {path_value!r} resolves outside --cwd.")
    if not resolved.is_file():
        raise ValueError(f"{label} {path_value!r} must be an existing regular file.")
    return resolved, resolved.relative_to(root).as_posix()


def build_dialogue_context(
    base_context: str,
    cwd: str,
    parent_answer_files: list[str] | tuple[str, ...],
    *,
    structured_output: bool = False,
) -> str:
    """Add the bounded dialogue contract and validated parent answer artifacts."""
    protocol = _STRUCTURED_PROTOCOL_CONTEXT if structured_output else _PROTOCOL_CONTEXT
    sections = [base_context.strip(), protocol.strip()]
    answers = []

    for answer_path in parent_answer_files:
        resolved, relative = _resolve_regular_file(
            answer_path, cwd, "Parent answer file"
        )
        size = resolved.stat().st_size
        if size > _MAX_ANSWER_FILE_BYTES:
            raise ValueError(
                f"Parent answer file {answer_path!r} is {size} bytes; maximum is "
                f"{_MAX_ANSWER_FILE_BYTES}."
            )
        content = resolved.read_text(encoding="utf-8")
        if not content.strip():
            raise ValueError(f"Parent answer file {answer_path!r} must not be empty.")
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        encoded = json.dumps(
            {"path": relative, "sha256": digest, "content": content},
            ensure_ascii=False,
        ).replace("</", "<\\/")
        answers.append(f"<parent_answer>\n{encoded}\n</parent_answer>")

    if answers:
        sections.append(
            "## Parent Answers From Prior Dialogue Turns\n\n" + "\n\n".join(answers)
        )

    return "\n\n".join(section for section in sections if section)


def _validate_string_list(value: object, field: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a JSON array of strings.")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{field} must contain only non-empty strings.")
    return [item.strip() for item in value]


def normalize_dialogue_result(result: dict, cwd: str) -> dict:
    """Validate and expose a bounded dialogue envelope from a successful run."""
    if result.get("status") != "success":
        return result

    structured_output = result.get("structured_output")
    if structured_output is not None:
        if not isinstance(structured_output, dict):
            return _protocol_error(result, "structured output must be a JSON object.")
        fields = set(structured_output)
        missing = _DIALOGUE_FIELDS - fields
        unexpected = fields - _DIALOGUE_FIELDS
        if missing:
            return _protocol_error(
                result,
                "structured output is missing required fields: "
                + ", ".join(sorted(missing))
                + ".",
            )
        if unexpected:
            return _protocol_error(
                result,
                "structured output has unexpected fields: "
                + ", ".join(sorted(unexpected))
                + ".",
            )
        human_report = structured_output.get("result")
        if not isinstance(human_report, str) or not human_report.strip():
            return _protocol_error(result, "result must be a non-empty string.")
        return _normalize_dialogue_payload(
            result,
            cwd,
            structured_output,
            human_report.strip(),
            terminal_protocol="structured_output",
        )

    text = result.get("result")
    if not isinstance(text, str):
        return _protocol_error(result, "result is not text.")

    matches = list(_ENVELOPE_PATTERN.finditer(text))
    if not matches:
        return _protocol_error(result, "required <subagent_result> envelope is missing.")
    if len(matches) != 1:
        return _protocol_error(result, "exactly one <subagent_result> envelope is required.")

    match = matches[0]
    if text[match.end() :].strip():
        return _protocol_error(result, "content after </subagent_result> is not allowed.")

    try:
        envelope = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        return _protocol_error(result, f"envelope contains invalid JSON: {exc.msg}.")
    if not isinstance(envelope, dict):
        return _protocol_error(result, "envelope must be a JSON object.")

    human_report = text[: match.start()].rstrip()
    return _normalize_dialogue_payload(
        result,
        cwd,
        envelope,
        human_report,
        terminal_protocol="assistant_envelope",
    )


def _normalize_dialogue_payload(
    result: dict,
    cwd: str,
    envelope: dict,
    human_report: str,
    *,
    terminal_protocol: str,
) -> dict:
    """Apply semantic dialogue rules after transport-level decoding."""

    try:
        agent_status = envelope.get("status")
        if agent_status not in _VALID_AGENT_STATUSES:
            allowed = ", ".join(sorted(_VALID_AGENT_STATUSES))
            raise ValueError(f"status must be one of: {allowed}.")

        summary = envelope.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            raise ValueError("summary must be a non-empty string.")
        summary = summary.strip()

        questions = _validate_string_list(envelope.get("questions", []), "questions")
        concerns = _validate_string_list(envelope.get("concerns", []), "concerns")
        if agent_status == "NEEDS_CONTEXT":
            if not 1 <= len(questions) <= 3:
                raise ValueError("NEEDS_CONTEXT requires one to three questions.")
        elif questions:
            raise ValueError("questions must be empty unless status is NEEDS_CONTEXT.")
        if agent_status == "DONE_WITH_CONCERNS" and not concerns:
            raise ValueError("DONE_WITH_CONCERNS requires at least one concern.")
        if agent_status != "DONE_WITH_CONCERNS" and concerns:
            raise ValueError(
                "concerns must be empty unless status is DONE_WITH_CONCERNS."
            )

        state_value = envelope.get("state_file")
        state_file = None
        if state_value is not None:
            if not isinstance(state_value, str) or not state_value.strip():
                raise ValueError("state_file must be null or a non-empty path string.")
            normalized_state_value = state_value.strip()
            if normalized_state_value.lower() != "null":
                _, state_file = _resolve_regular_file(
                    normalized_state_value, cwd, "State file"
                )
    except ValueError as exc:
        return _protocol_error(result, str(exc))

    normalized = {
        **result,
        "result": human_report or summary,
        "agent_status": agent_status,
        "summary": summary,
        "questions": questions,
        "concerns": concerns,
        "state_file": state_file,
        "protocol_version": 1,
        "terminal_protocol": terminal_protocol,
    }
    normalized.pop("structured_output", None)
    return normalized
