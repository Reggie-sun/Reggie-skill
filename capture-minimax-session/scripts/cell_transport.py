from __future__ import annotations

import json
import re
from typing import Any, Iterable, Pattern


CELL_MARKER_RE = re.compile(r"^Script running with cell ID (\d+)$")
WALL_TIME_RE = re.compile(r"^Wall time \d+(?:\.\d+)? seconds$")
FULL_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


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


def cell_ids_from_output(output: Any) -> set[str]:
    if not isinstance(output, str):
        return set()
    lines = output.strip().splitlines()
    if len(lines) == 1:
        marker_line = lines[0]
    elif (
        len(lines) == 3
        and WALL_TIME_RE.fullmatch(lines[1])
        and lines[2] == "Output:"
    ):
        marker_line = lines[0]
    else:
        return set()
    match = CELL_MARKER_RE.fullmatch(marker_line)
    return {match.group(1)} if match else set()


def wait_cell_id(payload: dict[str, Any]) -> str | None:
    if payload.get("type") != "function_call" or payload.get("name") != "wait":
        return None
    arguments = payload.get("arguments")
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return None
    if not isinstance(arguments, dict):
        return None
    value = arguments.get("cell_id")
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, str) and value.isdigit():
        return value
    return None


def activity_sessions_from_output(
    output: Any, activity_pattern: Pattern[str]
) -> set[str]:
    sessions: set[str] = set()
    for text in _text_values(output):
        for match in activity_pattern.finditer(text):
            session = match.group(3)
            if session:
                sessions.add(session)
    return sessions


def unique_uuid_prefix_replacements(sessions: Iterable[str]) -> dict[str, str]:
    session_set = set(sessions)
    full_sessions = {
        session for session in session_set if FULL_UUID_RE.fullmatch(session)
    }
    replacements: dict[str, str] = {}
    for session in session_set:
        if len(session) < 24 or session in full_sessions:
            continue
        matches = [full for full in full_sessions if full.startswith(session)]
        if len(matches) == 1:
            replacements[session] = matches[0]
    return replacements


def session_sets_intersect(
    left: set[str], right: set[str], universe: set[str] | None = None
) -> bool:
    if left.intersection(right):
        return True
    identity_universe = set(universe or ())
    identity_universe.update(left)
    identity_universe.update(right)
    replacements = unique_uuid_prefix_replacements(identity_universe)
    normalized_left = {replacements.get(session, session) for session in left}
    normalized_right = {replacements.get(session, session) for session in right}
    return bool(normalized_left.intersection(normalized_right))
