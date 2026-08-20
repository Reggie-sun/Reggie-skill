from __future__ import annotations

import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any


def _balanced_object_end(source: str, start: int) -> int | None:
    stack: list[str] = []
    quote: str | None = None
    escaped = False
    for index in range(start, len(source)):
        char = source[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {'"', "'", "`"}:
            quote = char
        elif char in "{[(":
            stack.append({"{": "}", "[": "]", "(": ")"}[char])
        elif char in "}])":
            if not stack or stack.pop() != char:
                return None
            if not stack:
                return index
    return None


def _exec_command_object_bodies(source: str) -> Iterable[str]:
    marker = "tools.exec_command"
    index = 0
    quote: str | None = None
    escaped = False
    while index < len(source):
        char = source[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            index += 1
            continue
        if source.startswith("//", index):
            newline = source.find("\n", index + 2)
            if newline < 0:
                return
            index = newline + 1
            continue
        if source.startswith("/*", index):
            comment_end = source.find("*/", index + 2)
            if comment_end < 0:
                return
            index = comment_end + 2
            continue
        if char in {'"', "'", "`"}:
            quote = char
            index += 1
            continue
        if not source.startswith(marker, index):
            index += 1
            continue
        if index > 0 and (
            source[index - 1].isalnum() or source[index - 1] in "_$."
        ):
            index += len(marker)
            continue
        cursor = index + len(marker)
        while cursor < len(source) and source[cursor].isspace():
            cursor += 1
        if cursor >= len(source) or source[cursor] != "(":
            index = cursor
            continue
        cursor += 1
        while cursor < len(source) and source[cursor].isspace():
            cursor += 1
        if cursor >= len(source) or source[cursor] != "{":
            index = cursor
            continue
        end = _balanced_object_end(source, cursor)
        if end is None:
            return
        yield source[cursor + 1 : end]
        index = end + 1


def _top_level_fields(object_body: str) -> Iterable[str]:
    start = 0
    stack: list[str] = []
    quote: str | None = None
    escaped = False
    for index, char in enumerate(object_body):
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {'"', "'", "`"}:
            quote = char
        elif char in "{[(":
            stack.append({"{": "}", "[": "]", "(": ")"}[char])
        elif char in "}])":
            if not stack or stack.pop() != char:
                return
        elif char == "," and not stack:
            yield object_body[start:index].strip()
            start = index + 1
    if not stack and quote is None:
        yield object_body[start:].strip()


def contains_dynamic_runner_command(raw_input: Any) -> bool:
    if not isinstance(raw_input, str):
        return False
    derived = {
        command: arguments
        for command, arguments in re.findall(
            r"(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*"
            r"([A-Za-z_$][A-Za-z0-9_$]*)\s*\.map\([^)]*\)\.join\([^)]*\)\s*;",
            raw_input,
            re.DOTALL,
        )
    }
    argument_variables: set[str] = set()
    direct_re = re.compile(
        r"([A-Za-z_$][A-Za-z0-9_$]*)\s*\.map\([^)]*\)\.join\([^)]*\)\s*",
        re.DOTALL,
    )
    for body in _exec_command_object_bodies(raw_input):
        for property_text in _top_level_fields(body):
            if property_text == "cmd" and "cmd" in derived:
                argument_variables.add(derived["cmd"])
                continue
            match = re.fullmatch(
                r'(?:(?:"cmd")|(?:\'cmd\')|cmd)\s*:\s*(.+)',
                property_text,
                re.DOTALL,
            )
            if match is None:
                continue
            expression = match.group(1).strip()
            direct_match = direct_re.fullmatch(expression)
            if direct_match is not None:
                argument_variables.add(direct_match.group(1))
            elif expression in derived:
                argument_variables.add(derived[expression])
    for argument_variable in argument_variables:
        variable = re.escape(argument_variable)
        array_match = re.search(
            rf"(?:const|let|var)\s+{variable}\s*=\s*\[\s*"
            r'("(?:\\.|[^"\\])*")\s*,\s*("(?:\\.|[^"\\])*")',
            raw_input,
            re.DOTALL,
        )
        if array_match is None:
            continue
        try:
            executable = json.loads(array_match.group(1))
            runner = json.loads(array_match.group(2))
        except json.JSONDecodeError:
            continue
        if (
            isinstance(executable, str)
            and Path(executable).name.startswith("python")
            and isinstance(runner, str)
            and Path(runner).name == "run_subagent.py"
        ):
            return True
    return False
