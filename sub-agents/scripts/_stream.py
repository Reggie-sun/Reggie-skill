from __future__ import annotations

import json
import re
from pathlib import Path

from _builder import parse_command_argv

from _constants import SUPPORTED_CLIS_HELP


_TOOL_ERROR_LOOP_THRESHOLD = 3
_POLICY_PERMISSION_DENIAL_MARKERS = (
    "not in allowedtools",
    "tool use was denied",
    "because claude code is running in don't ask mode",
)
_DIALOGUE_ENVELOPE_AT_END = re.compile(
    r"<subagent_result>.*</subagent_result>\s*\Z",
    re.DOTALL,
)


def _tool_result_text(content: object) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return " ".join(
            part
            for item in content
            if (part := _tool_result_text(item))
        ).strip()
    if isinstance(content, dict):
        for key in ("text", "content", "message", "error"):
            if key in content:
                return _tool_result_text(content[key])
    return ""


def _error_signature(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def _is_policy_permission_denial(signature: str, tool_name: str | None) -> bool:
    if any(marker in signature for marker in _POLICY_PERMISSION_DENIAL_MARKERS):
        return True
    if not tool_name:
        return False
    tool = re.escape(tool_name.casefold())
    return bool(
        re.search(
            rf"\bpermission to use {tool}\b.*\bhas been denied\b",
            signature,
        )
    )


def _command_family(command: str | None) -> tuple[str, ...] | None:
    if command is None:
        return None
    try:
        return ("argv", *parse_command_argv(command))
    except ValueError:
        return ("raw", command)


def _is_string_delimiter(text: str, index: int) -> bool:
    """A quote is a delimiter unless an odd number of backslashes escape it."""
    backslashes = 0
    position = index - 1
    while position >= 0 and text[position] == "\\":
        backslashes += 1
        position -= 1
    return backslashes % 2 == 0


def _trailing_object_start(text: str) -> int:
    """Index of the '{' opening the object that closes the text, or -1."""
    depth = 0
    in_string = False
    for index in range(len(text) - 1, -1, -1):
        char = text[index]
        if char == '"' and _is_string_delimiter(text, index):
            in_string = not in_string
        elif in_string:
            continue
        elif char == "}":
            depth += 1
        elif char == "{":
            depth -= 1
            if depth == 0:
                return index
    return -1


def _extract_trailing_json_object(text: str) -> str:
    stripped = text.strip()
    if not stripped.endswith("}"):
        return text

    start = _trailing_object_start(stripped)
    if start < 0:
        return text

    try:
        value, end = json.JSONDecoder().raw_decode(stripped, start)
    except json.JSONDecodeError:
        return text
    if isinstance(value, dict) and end == len(stripped):
        return stripped[start:end]
    return text


def _grok_json_result(data: dict) -> dict | None:
    if not isinstance(data.get("text"), str):
        return None
    return {
        "type": "result",
        "result": _extract_trailing_json_object(data["text"]),
        "status": "success" if data.get("stopReason") == "EndTurn" else "partial",
        "stop_reason": data.get("stopReason"),
        "session_id": data.get("sessionId"),
    }


class StreamProcessor:
    """Normalize supported CLI streams into a result payload."""

    def __init__(
        self,
        cli: str,
        allowed_commands: tuple[str, ...] = (),
        count_tool_requests_as_progress: bool = False,
        allow_structured_output: bool = False,
        cwd: str = "/",
        required_evidence_paths: tuple[str, ...] = (),
    ):
        self.cli = cli
        try:
            self._line_processor = _LINE_PROCESSORS[cli]
        except KeyError as e:
            raise ValueError(
                f"Unsupported CLI {cli!r}. Choose one of: {SUPPORTED_CLIS_HELP}."
            ) from e
        self.result_json = None
        self.gemini_parts = []
        self.codex_messages = []
        self.opencode_parts = []
        self.session_id = None
        self.partial_text_parts = []
        self.last_assistant_text: str | None = None
        self.last_event = "started"
        self.progress_revision = 0
        self._semantic_events = set()
        self.allowed_commands = allowed_commands
        self.count_tool_requests_as_progress = count_tool_requests_as_progress
        self.allow_structured_output = allow_structured_output
        self._cwd = Path(cwd).resolve()
        self._required_evidence_paths = tuple(required_evidence_paths)
        self._required_evidence_set = set(required_evidence_paths)
        self._tool_evidence_paths: dict[str, str] = {}
        self._observed_evidence_paths: set[str] = set()
        self._allowed_command_argv = tuple(
            (command, parse_command_argv(command)) for command in allowed_commands
        )
        self._tool_commands: dict[str, str] = {}
        self._tool_names: dict[str, str] = {}
        self._structured_tool_inputs: dict[str, dict] = {}
        self._latest_structured_tool_id: str | None = None
        self._confirmed_structured_output: dict | None = None
        self._last_tool_command: str | None = None
        self._last_tool_name: str | None = None
        self._permission_denial_count = 0
        self._permission_denial_tool: str | None = None
        self._permission_denial_command_families: set[tuple[str, ...]] = set()
        self._last_error_signature: str | None = None
        self._last_error_tool: str | None = None
        self._last_error_command_family: tuple[str, ...] | None = None
        self._equivalent_error_count = 0
        self._tool_error_loop: dict | None = None

    def _grant_match(self, attempted_command: str | None) -> str:
        if not attempted_command:
            return "attempted_command_unavailable"
        if attempted_command in self.allowed_commands:
            return "exact_grant_present"
        try:
            attempted_argv = parse_command_argv(attempted_command)
        except ValueError:
            return "attempted_command_unparseable"
        if any(attempted_argv == argv for _, argv in self._allowed_command_argv):
            return "argv_equivalent_exact_string_mismatch"
        return "command_not_authorized"

    def _observe_tool_error(self, item: dict) -> None:
        error_text = _tool_result_text(item.get("content")) or "Unknown tool error"
        signature = _error_signature(error_text)
        tool_use_id = item.get("tool_use_id")
        tool_name = (
            self._tool_names.get(tool_use_id)
            if isinstance(tool_use_id, str)
            else None
        ) or self._last_tool_name
        attempted_command = (
            self._tool_commands.get(tool_use_id)
            if isinstance(tool_use_id, str)
            else None
        )
        if attempted_command is None and tool_name == "Bash":
            attempted_command = self._last_tool_command
        command_family = _command_family(attempted_command)
        is_permission_denial = _is_policy_permission_denial(signature, tool_name)
        if is_permission_denial:
            if tool_name == self._permission_denial_tool:
                self._permission_denial_count += 1
            else:
                self._permission_denial_tool = tool_name
                self._permission_denial_count = 1
                self._permission_denial_command_families.clear()
            if command_family is not None:
                self._permission_denial_command_families.add(command_family)

        if signature == self._last_error_signature and tool_name == self._last_error_tool:
            self._equivalent_error_count += 1
        else:
            self._last_error_signature = signature
            self._last_error_tool = tool_name
            self._equivalent_error_count = 1
        self._last_error_command_family = command_family

        # A fresh, non-interactive invocation cannot change its tool grants.
        # Continuing after any permission denial only invites the model to
        # retry or rephrase a command that can never become authorized.
        if is_permission_denial:
            self._tool_error_loop = {
                "kind": "permission_denial_loop",
                "occurrences": self._permission_denial_count,
                "tool": tool_name,
                "attempted_command": attempted_command,
                "allowed_commands": list(self.allowed_commands),
                "grant_match": self._grant_match(attempted_command),
                "tool_error": error_text,
            }
        elif self._equivalent_error_count >= _TOOL_ERROR_LOOP_THRESHOLD:
            self._tool_error_loop = {
                "kind": "repeated_tool_error",
                "occurrences": self._equivalent_error_count,
                "tool": tool_name,
                "attempted_command": attempted_command,
                "allowed_commands": list(self.allowed_commands),
                "grant_match": self._grant_match(attempted_command),
                "tool_error": error_text,
            }

    def _observe_tool_success(self, item: dict) -> None:
        tool_use_id = item.get("tool_use_id")
        tool_name = (
            self._tool_names.get(tool_use_id)
            if isinstance(tool_use_id, str)
            else None
        ) or self._last_tool_name
        command = (
            self._tool_commands.get(tool_use_id)
            if isinstance(tool_use_id, str)
            else None
        )
        command_family = _command_family(command)
        clears_denial = tool_name != "Bash" or (
            command_family in self._permission_denial_command_families
        )
        if tool_name == self._permission_denial_tool and clears_denial:
            self._permission_denial_count = 0
            self._permission_denial_tool = None
            self._permission_denial_command_families.clear()
        clears_equivalent_error = (
            tool_name != "Bash" or command_family == self._last_error_command_family
        )
        if tool_name == self._last_error_tool and clears_equivalent_error:
            self._last_error_signature = None
            self._last_error_tool = None
            self._last_error_command_family = None
            self._equivalent_error_count = 0
        if isinstance(tool_use_id, str):
            evidence_path = self._tool_evidence_paths.get(tool_use_id)
            if evidence_path is not None:
                self._observed_evidence_paths.add(evidence_path)

    def _normalize_observed_evidence_path(self, value: object) -> str | None:
        if not isinstance(value, str) or not value.strip():
            return None
        supplied = Path(value)
        candidate = supplied if supplied.is_absolute() else self._cwd / supplied
        try:
            resolved = candidate.resolve()
            if not resolved.is_relative_to(self._cwd):
                return None
            if not resolved.is_file():
                return None
            relative = resolved.relative_to(self._cwd).as_posix()
        except (OSError, ValueError):
            return None
        return relative if relative in self._required_evidence_set else None

    def _mark_semantic_progress(self, item: dict) -> None:
        semantic_item = {
            key: value for key, value in item.items() if key not in ("id", "tool_use_id")
        }
        fingerprint = json.dumps(
            semantic_item, sort_keys=True, ensure_ascii=False, default=str
        )
        if fingerprint in self._semantic_events:
            return
        self._semantic_events.add(fingerprint)
        self.progress_revision += 1

    def _observe_data(self, data: dict) -> None:
        session_id = data.get("session_id") or data.get("sessionId")
        if isinstance(session_id, str) and session_id:
            self.session_id = session_id

        event_type = data.get("type")
        if isinstance(event_type, str) and event_type:
            self.last_event = event_type

        if event_type not in ("assistant", "user"):
            return

        message = data.get("message")
        if not isinstance(message, dict):
            return
        content = message.get("content")
        if not isinstance(content, list):
            return

        assistant_text_parts = []
        for item in content:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")
            if item_type == "tool_use":
                name = item.get("name")
                self.last_event = f"tool:{name}" if isinstance(name, str) else "tool"
                if self.count_tool_requests_as_progress:
                    self._mark_semantic_progress(item)
                if isinstance(name, str):
                    self._last_tool_name = name
                tool_input = item.get("input")
                command = tool_input.get("command") if isinstance(tool_input, dict) else None
                tool_id = item.get("id") or item.get("tool_use_id")
                if isinstance(tool_id, str) and isinstance(name, str):
                    self._tool_names[tool_id] = name
                if isinstance(tool_id, str) and isinstance(tool_input, dict):
                    evidence_value = None
                    if name == "Read":
                        evidence_value = tool_input.get("file_path")
                    elif name == "Grep":
                        evidence_value = tool_input.get("path")
                    evidence_path = self._normalize_observed_evidence_path(
                        evidence_value
                    )
                    if evidence_path is not None:
                        self._tool_evidence_paths[tool_id] = evidence_path
                if self.allow_structured_output and name == "StructuredOutput":
                    self._latest_structured_tool_id = None
                    self._confirmed_structured_output = None
                    self._structured_tool_inputs.clear()
                if (
                    self.allow_structured_output
                    and name == "StructuredOutput"
                    and isinstance(tool_id, str)
                    and isinstance(tool_input, dict)
                ):
                    self._latest_structured_tool_id = tool_id
                    self._structured_tool_inputs[tool_id] = dict(tool_input)
                if name == "Bash" and isinstance(command, str):
                    self._last_tool_command = command
                    if isinstance(tool_id, str):
                        self._tool_commands[tool_id] = command
            elif item_type == "tool_result":
                self.last_event = "tool_result:error" if item.get("is_error") else "tool_result"
                if item.get("is_error"):
                    tool_use_id = item.get("tool_use_id")
                    if tool_use_id == self._latest_structured_tool_id:
                        self._latest_structured_tool_id = None
                        self._confirmed_structured_output = None
                    self._observe_tool_error(item)
                else:
                    self._observe_tool_success(item)
                    tool_use_id = item.get("tool_use_id")
                    if (
                        self.allow_structured_output
                        and isinstance(tool_use_id, str)
                        and tool_use_id == self._latest_structured_tool_id
                        and self._tool_names.get(tool_use_id) == "StructuredOutput"
                        and tool_use_id in self._structured_tool_inputs
                    ):
                        self._confirmed_structured_output = (
                            self._structured_tool_inputs[tool_use_id]
                        )
                    self._mark_semantic_progress(item)
            elif item_type == "thinking":
                self.last_event = "thinking"
            elif item_type == "text":
                self.last_event = "assistant"
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    self._mark_semantic_progress(item)
                    assistant_text_parts.append(text.strip())
                    # Partial output is diagnostic context, not an unbounded transcript.
                    current_size = sum(len(part) for part in self.partial_text_parts)
                    if current_size < 64 * 1024:
                        self.partial_text_parts.append(text.strip())
        if event_type == "assistant" and assistant_text_parts:
            self.last_assistant_text = "\n".join(assistant_text_parts)

    def _process_gemini_line(self, data: dict) -> bool:
        if data.get("type") == "message" and data.get("role") == "assistant":
            content = data.get("content", "")
            if isinstance(content, str):
                self.gemini_parts.append(content)
            return False

        if data.get("type") == "result":
            self.result_json = {
                "type": "result",
                "result": "".join(self.gemini_parts),
                "status": data.get("status", "success"),
            }
            return True

        return False

    def _process_codex_line(self, data: dict) -> bool:
        if data.get("type") == "item.completed":
            item = data.get("item", {})
            if item.get("type") == "agent_message" and isinstance(item.get("text"), str):
                self.codex_messages.append(item["text"])
            return False

        if data.get("type") == "turn.completed":
            self.result_json = {
                "type": "result",
                "result": "\n".join(self.codex_messages),
                "status": "success",
            }
            return True

        return False

    def _process_opencode_line(self, data: dict) -> bool:
        part = data.get("part")
        if not isinstance(part, dict):
            return False

        if data.get("type") == "text":
            text = part.get("text")
            if isinstance(text, str):
                self.opencode_parts.append(text)
            return False

        if data.get("type") != "step_finish":
            return False

        reason = part.get("reason")
        if reason == "tool-calls" or reason is None:
            return False
        self.result_json = {
            "type": "result",
            "result": "".join(self.opencode_parts),
            "status": "success" if reason == "stop" else "partial",
            "stop_reason": reason,
        }
        return True

    def _process_grok_line(self, data: dict) -> bool:
        grok_result = _grok_json_result(data)
        if grok_result is None:
            return False
        self.result_json = grok_result
        return True

    def _process_result_line(self, data: dict) -> bool:
        if data.get("type") != "result":
            return False

        subtype = data.get("subtype")
        is_error = (
            data.get("is_error") is True
            or data.get("status") == "error"
            or (isinstance(subtype, str) and subtype.startswith("error_"))
        )
        if is_error:
            self.result_json = {**data, "status": "error"}
            return True

        has_text_result = isinstance(data.get("result"), str)
        has_structured_result = self.allow_structured_output and isinstance(
            data.get("structured_output"), dict
        )
        if not has_text_result and not has_structured_result:
            return False
        self.result_json = data
        return True

    def process_line(self, line: str) -> bool:
        """Process one line. Returns True when a terminal event is reached."""
        line = line.strip()
        if not line or self.result_json is not None:
            return False

        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            return False

        self._observe_data(data)
        return self._line_processor(self, data)

    def process_complete_output(self, output: str) -> bool:
        """Process a complete non-NDJSON payload. Returns True when parsed."""
        if self.result_json is not None:
            return False

        try:
            data = json.loads(output)
        except json.JSONDecodeError:
            return False

        if isinstance(data, dict) and self.cli == "grok":
            return self._process_grok_line(data)

        return False

    def promote_clean_exit_dialogue_result(self) -> bool:
        """Recover a final dialogue envelope when Claude omits ``type=result``."""
        if self.result_json is not None or not self.last_assistant_text:
            return False
        report = self.last_assistant_text.strip()
        if not _DIALOGUE_ENVELOPE_AT_END.search(report):
            return False
        self.result_json = {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": report,
            "terminal_source": "assistant_envelope",
        }
        if self.session_id:
            self.result_json["session_id"] = self.session_id
        return True

    def promote_clean_exit_structured_result(self) -> bool:
        """Recover a StructuredOutput payload confirmed by its tool result."""
        if (
            self.result_json is not None
            or not self.allow_structured_output
            or self._confirmed_structured_output is None
        ):
            return False
        self.result_json = {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "structured_output": self._confirmed_structured_output,
            "terminal_source": "structured_tool_result",
        }
        if self.session_id:
            self.result_json["session_id"] = self.session_id
        return True

    def get_result(self):
        return self.result_json

    def get_partial_result(self) -> dict | None:
        if self.result_json is not None:
            return self.result_json
        if not self.partial_text_parts and self.last_event == "started" and not self.session_id:
            return None

        result_text = "\n".join(self.partial_text_parts).strip()
        if not result_text:
            result_text = f"Sub-agent was active through {self.last_event} but returned no final report."
        partial = {
            "type": "partial",
            "result": result_text,
            "status": "partial",
            "last_event": self.last_event,
        }
        if self.session_id:
            partial["session_id"] = self.session_id
        return partial

    def get_progress(self) -> tuple[str, str | None]:
        return self.last_event, self.session_id

    def get_progress_revision(self) -> int:
        return self.progress_revision

    def get_tool_error_loop(self) -> dict | None:
        return self._tool_error_loop

    def get_observed_evidence_paths(self) -> tuple[str, ...]:
        return tuple(
            path
            for path in self._required_evidence_paths
            if path in self._observed_evidence_paths
        )


_LINE_PROCESSORS = {
    "codex": StreamProcessor._process_codex_line,
    "claude": StreamProcessor._process_result_line,
    "cursor-agent": StreamProcessor._process_result_line,
    "glm": StreamProcessor._process_result_line,
    "kimi": StreamProcessor._process_result_line,
    "minimax": StreamProcessor._process_result_line,
    "grok": StreamProcessor._process_grok_line,
    "gemini": StreamProcessor._process_gemini_line,
    "opencode": StreamProcessor._process_opencode_line,
}
