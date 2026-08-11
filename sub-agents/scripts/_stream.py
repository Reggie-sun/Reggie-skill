from __future__ import annotations

import json

from _constants import SUPPORTED_CLIS_HELP


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

    def __init__(self, cli: str):
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
        self.last_event = "started"
        self.progress_revision = 0
        self._semantic_events = set()

    def _mark_semantic_progress(self, item: dict) -> None:
        fingerprint = json.dumps(item, sort_keys=True, ensure_ascii=False, default=str)
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

        for item in content:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")
            if item_type == "tool_use":
                name = item.get("name")
                self.last_event = f"tool:{name}" if isinstance(name, str) else "tool"
                self._mark_semantic_progress(item)
            elif item_type == "tool_result":
                self.last_event = "tool_result:error" if item.get("is_error") else "tool_result"
                self._mark_semantic_progress(item)
            elif item_type == "thinking":
                self.last_event = "thinking"
                self._mark_semantic_progress(item)
            elif item_type == "text":
                self.last_event = "assistant"
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    self._mark_semantic_progress(item)
                    # Partial output is diagnostic context, not an unbounded transcript.
                    current_size = sum(len(part) for part in self.partial_text_parts)
                    if current_size < 64 * 1024:
                        self.partial_text_parts.append(text.strip())

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

        if not isinstance(data.get("result"), str):
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
