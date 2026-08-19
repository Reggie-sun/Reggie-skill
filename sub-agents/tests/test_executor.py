from __future__ import annotations

import io
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from _builder import AgentInvocation  # noqa: E402
from _executor import (  # noqa: E402
    _drive_process,
    _spawn_and_drive,
    build_final_response,
    execute_agent,
)


def _python_process(source: str) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-u", "-c", source],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        start_new_session=True,
    )


def _drive_test_process(
    source: str,
    progress: io.StringIO,
    *,
    cli: str = "claude",
    timeout_ms: int = 100,
    semantic_timeout_ms: int | None = None,
    allowed_commands: tuple[str, ...] = (),
    fail_fast_tool_errors: bool = True,
    allow_dialogue_fallback: bool = False,
    allow_structured_output: bool = False,
    cwd: str = "/tmp",
    required_evidence_paths: tuple[str, ...] = (),
) -> dict:
    process = _python_process(source)
    try:
        return _drive_process(
            process,
            cli,
            timeout_ms=timeout_ms,
            heartbeat_sec=0.02,
            progress_stream=progress,
            semantic_timeout_ms=semantic_timeout_ms,
            allowed_commands=allowed_commands,
            fail_fast_tool_errors=fail_fast_tool_errors,
            allow_dialogue_fallback=allow_dialogue_fallback,
            allow_structured_output=allow_structured_output,
            cwd=cwd,
            required_evidence_paths=required_evidence_paths,
        )
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()


def _event_source(events: list[dict], exit_code: int = 0) -> str:
    return (
        "import json\n"
        f"events = {events!r}\n"
        "for event in events:\n"
        "    print(json.dumps(event), flush=True)\n"
        f"raise SystemExit({exit_code})\n"
    )


def _structured_tool_use(tool_id: str, payload: dict) -> dict:
    return {
        "type": "assistant",
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "id": tool_id,
                    "name": "StructuredOutput",
                    "input": payload,
                }
            ]
        },
    }


def _tool_result(tool_id: str, *, is_error: bool = False) -> dict:
    item = {
        "type": "tool_result",
        "tool_use_id": tool_id,
        "content": "failed" if is_error else "success",
    }
    if is_error:
        item["is_error"] = True
    return {
        "type": "user",
        "message": {"content": [item]},
    }


class ExecutorLivenessTests(unittest.TestCase):
    def test_execute_agent_attaches_sanitized_runner_context(self) -> None:
        invocation = AgentInvocation(
            cli="minimax",
            prompt="inspect",
            cwd="/tmp",
            permission="read-only",
            model="MiniMax-M3",
            effort="high",
            structured_output_schema='{"type":"object"}',
        )

        with (
            patch(
                "_executor.build_invocation_args",
                return_value=(
                    "claude",
                    [
                        "--tools",
                        "Read,Glob,Grep,StructuredOutput",
                        "--model",
                        "MiniMax-M3",
                        "--effort",
                        "high",
                    ],
                    None,
                ),
            ),
            patch(
                "_executor._spawn_and_drive",
                return_value={"status": "success", "cli": "minimax"},
            ),
        ):
            result = execute_agent(invocation, timeout_ms=600_000)

        self.assertEqual(
            result["runner_context"],
            {
                "model": "MiniMax-M3",
                "effort": "high",
                "permission": "read-only",
                "tools_mode": "explicit",
                "tools": ["Read", "Glob", "Grep", "StructuredOutput"],
            },
        )

    def test_runner_context_uses_resolved_env_model_and_rejects_prose(self) -> None:
        invocation = AgentInvocation(
            cli="minimax",
            prompt="inspect",
            cwd="/tmp",
            permission="read-only",
            effort="high with sk-cp-secret-value",
        )

        with (
            patch(
                "_executor.build_invocation_args",
                return_value=(
                    "claude",
                    ["--tools", "Read,Glob,Grep"],
                    {"ANTHROPIC_MODEL": "MiniMax-M3"},
                ),
            ),
            patch(
                "_executor._spawn_and_drive",
                return_value={"status": "success", "cli": "minimax"},
            ),
        ):
            result = execute_agent(invocation, timeout_ms=600_000)

        self.assertEqual(result["runner_context"]["model"], "MiniMax-M3")
        self.assertEqual(result["runner_context"]["effort"], "default")
        self.assertNotIn("secret-value", str(result["runner_context"]))

    def test_prompt_named_tools_does_not_confuse_runner_context(self) -> None:
        invocation = AgentInvocation(
            cli="minimax",
            prompt="--tools",
            cwd="/tmp",
            permission="yolo",
        )

        with (
            patch(
                "_executor.build_invocation_args",
                return_value=("claude", ["--dangerously-skip-permissions", "-p", "--tools"], None),
            ),
            patch(
                "_executor.resolved_tool_context",
                return_value=("default", ()),
            ),
            patch(
                "_executor._spawn_and_drive",
                return_value={"status": "success", "cli": "minimax"},
            ),
        ):
            result = execute_agent(invocation, timeout_ms=600_000)

        self.assertEqual(result["runner_context"]["tools_mode"], "default")
        self.assertEqual(result["runner_context"]["tools"], [])

    def test_safe_edit_uses_configured_timeout_as_semantic_cap(self) -> None:
        invocation = AgentInvocation(
            cli="minimax",
            prompt="implement",
            cwd="/tmp",
            permission="safe-edit",
            allowed_paths=("owned.py",),
        )

        with (
            patch(
                "_executor.build_invocation_args",
                return_value=("claude", ["-p", "implement"], None),
            ),
            patch("_executor._spawn_and_drive", return_value={"status": "success"}) as spawn,
        ):
            execute_agent(invocation, timeout_ms=1_800_000)

        self.assertEqual(spawn.call_args.kwargs["semantic_timeout_ms"], 1_800_000)
        self.assertTrue(spawn.call_args.kwargs["fail_fast_tool_errors"])

    def test_read_only_uses_configured_semantic_cap_without_safe_edit_fail_fast(self) -> None:
        invocation = AgentInvocation(
            cli="minimax",
            prompt="inspect",
            cwd="/tmp",
            permission="read-only",
        )

        with (
            patch(
                "_executor.build_invocation_args",
                return_value=("claude", ["-p", "inspect"], None),
            ),
            patch("_executor._spawn_and_drive", return_value={"status": "success"}) as spawn,
        ):
            execute_agent(invocation, timeout_ms=600_000)

        self.assertFalse(spawn.call_args.kwargs["fail_fast_tool_errors"])
        self.assertEqual(spawn.call_args.kwargs["semantic_timeout_ms"], 600_000)

    def test_activity_extends_idle_timeout_and_emits_progress(self) -> None:
        source = """
import json
import time
for index in range(5):
    print(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": f"step {index}"}]}}), flush=True)
    time.sleep(0.06)
print(json.dumps({"type": "result", "result": "DONE", "session_id": "session-active"}), flush=True)
"""
        progress = io.StringIO()

        result = _drive_test_process(source, progress)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["result"], "DONE")
        self.assertIn("event=assistant", progress.getvalue())
        self.assertNotIn("step 0", progress.getvalue())


    def test_missing_required_evidence_fails_closed_after_model_success(self) -> None:
        structured_output = {
            "status": "DONE_WITH_CONCERNS",
            "summary": "No lifecycle change required",
            "result": "The service can be reused unchanged.",
            "questions": [],
            "state_file": None,
            "concerns": ["Validator semantics need a deeper read."],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "owner.py").write_text("OWNER = True\n", encoding="utf-8")
            (root / "validator.py").write_text("VALID = True\n", encoding="utf-8")
            events = [
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "read-owner",
                                "name": "Read",
                                "input": {"file_path": str(root / "owner.py")},
                            }
                        ]
                    },
                },
                _tool_result("read-owner"),
                {
                    "type": "result",
                    "subtype": "success",
                    "is_error": False,
                    "structured_output": structured_output,
                },
            ]

            result = _drive_test_process(
                _event_source(events),
                io.StringIO(),
                timeout_ms=1_000,
                allow_structured_output=True,
                cwd=temp_dir,
                required_evidence_paths=("owner.py", "validator.py"),
            )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["agent_status"], "BLOCKED")
        self.assertEqual(result["termination_reason"], "evidence_incomplete")
        self.assertEqual(result["observed_evidence_paths"], ["owner.py"])
        self.assertEqual(result["blocker"]["missing_paths"], ["validator.py"])
        self.assertEqual(result["result"], "")
        self.assertEqual(result["summary"], "Required evidence incomplete")
        self.assertNotIn("structured_output", result)

    def test_successful_read_and_file_scoped_grep_satisfy_evidence_gate(self) -> None:
        structured_output = {
            "status": "DONE",
            "summary": "Mapped both owners",
            "result": "Both lifecycle owners were inspected.",
            "questions": [],
            "state_file": None,
            "concerns": [],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "owner.py").write_text("OWNER = True\n", encoding="utf-8")
            (root / "validator.py").write_text("VALID = True\n", encoding="utf-8")
            events = [
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "read-owner",
                                "name": "Read",
                                "input": {"file_path": "owner.py"},
                            },
                            {
                                "type": "tool_use",
                                "id": "grep-validator",
                                "name": "Grep",
                                "input": {
                                    "pattern": "validate",
                                    "path": "validator.py",
                                },
                            },
                        ]
                    },
                },
                _tool_result("read-owner"),
                _tool_result("grep-validator"),
                {
                    "type": "result",
                    "subtype": "success",
                    "is_error": False,
                    "structured_output": structured_output,
                },
            ]

            result = _drive_test_process(
                _event_source(events),
                io.StringIO(),
                timeout_ms=1_000,
                allow_structured_output=True,
                cwd=temp_dir,
                required_evidence_paths=("owner.py", "validator.py"),
            )

        self.assertEqual(result["status"], "success")
        self.assertEqual(
            result["observed_evidence_paths"],
            ["owner.py", "validator.py"],
        )

    def test_failed_read_does_not_satisfy_evidence_gate(self) -> None:
        events = [
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "read-owner",
                            "name": "Read",
                            "input": {"file_path": "owner.py"},
                        }
                    ]
                },
            },
            _tool_result("read-owner", is_error=True),
            {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "structured_output": {
                    "status": "DONE",
                    "summary": "Mapped owner",
                    "result": "Owner inspected.",
                    "questions": [],
                    "state_file": None,
                    "concerns": [],
                },
            },
        ]

        result = _drive_test_process(
            _event_source(events),
            io.StringIO(),
            timeout_ms=1_000,
            allow_structured_output=True,
            fail_fast_tool_errors=False,
            cwd="/tmp/project",
            required_evidence_paths=("owner.py",),
        )

        self.assertEqual(result["termination_reason"], "evidence_incomplete")
        self.assertEqual(result["observed_evidence_paths"], [])

    def test_directory_scoped_grep_does_not_satisfy_file_evidence_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            (Path(temp_dir) / "owner.py").mkdir()
            events = [
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "grep-owner",
                                "name": "Grep",
                                "input": {"pattern": "owner", "path": "owner.py"},
                            }
                        ]
                    },
                },
                _tool_result("grep-owner"),
                {
                    "type": "result",
                    "subtype": "success",
                    "is_error": False,
                    "structured_output": {
                        "status": "DONE",
                        "summary": "Mapped owner",
                        "result": "Owner inspected.",
                        "questions": [],
                        "state_file": None,
                        "concerns": [],
                    },
                },
            ]

            result = _drive_test_process(
                _event_source(events),
                io.StringIO(),
                timeout_ms=1_000,
                allow_structured_output=True,
                cwd=temp_dir,
                required_evidence_paths=("owner.py",),
            )

        self.assertEqual(result["termination_reason"], "evidence_incomplete")
        self.assertEqual(result["observed_evidence_paths"], [])

    def test_symlinked_read_does_not_satisfy_file_evidence_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "actual.py").write_text("OWNER = True\n", encoding="utf-8")
            (root / "owner.py").symlink_to(root / "actual.py")
            events = [
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "read-owner",
                                "name": "Read",
                                "input": {"file_path": "owner.py"},
                            }
                        ]
                    },
                },
                _tool_result("read-owner"),
                {
                    "type": "result",
                    "subtype": "success",
                    "is_error": False,
                    "structured_output": {
                        "status": "DONE",
                        "summary": "Mapped owner",
                        "result": "Owner inspected.",
                        "questions": [],
                        "state_file": None,
                        "concerns": [],
                    },
                },
            ]

            result = _drive_test_process(
                _event_source(events),
                io.StringIO(),
                timeout_ms=1_000,
                allow_structured_output=True,
                cwd=temp_dir,
                required_evidence_paths=("owner.py",),
            )

        self.assertEqual(result["termination_reason"], "evidence_incomplete")
        self.assertEqual(result["observed_evidence_paths"], [])

    def test_idle_timeout_returns_partial_text_and_session_id(self) -> None:
        source = """
import json
import time
print(json.dumps({"type": "system", "session_id": "session-partial"}), flush=True)
print(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "work in progress"}]}}), flush=True)
time.sleep(2)
"""

        result = _drive_test_process(source, io.StringIO())

        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["exit_code"], 124)
        self.assertEqual(result["session_id"], "session-partial")
        self.assertIn("work in progress", result["result"])
        self.assertIn("idle", result["error"].lower())

    def test_repeated_tool_result_does_not_extend_stagnation_deadline(self) -> None:
        source = """
import json
import time
event = {
    "type": "user",
    "message": {
        "content": [
            {"type": "tool_result", "tool_use_id": "tool-1", "content": "unchanged"}
        ]
    },
}
for _ in range(10):
    print(json.dumps(event), flush=True)
    time.sleep(0.04)
time.sleep(2)
"""

        with patch("_executor._MAX_STAGNATION_MS", 100):
            result = _drive_test_process(source, io.StringIO(), timeout_ms=1_000)

        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["exit_code"], 124)
        self.assertIn("stagnation", result["error"].lower())

    def test_read_only_distinct_tool_requests_extend_semantic_progress(self) -> None:
        source = r'''
import json
import time
for index in range(5):
    print(json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Read", "id": f"tool-{index}", "input": {"file_path": f"module-{index}.py"}}]}}), flush=True)
    time.sleep(0.06)
print(json.dumps({"type": "result", "result": "DONE"}), flush=True)
'''

        with patch("_executor._MAX_STAGNATION_MS", 100):
            result = _drive_test_process(
                source,
                io.StringIO(),
                timeout_ms=1_000,
                fail_fast_tool_errors=False,
            )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["result"], "DONE")

    def test_read_only_repeated_identical_tool_request_is_not_progress(self) -> None:
        source = r'''
import json
import time
for index in range(10):
    print(json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Read", "id": f"tool-{index}", "input": {"file_path": "same.py"}}]}}), flush=True)
    time.sleep(0.04)
time.sleep(2)
'''

        with patch("_executor._MAX_STAGNATION_MS", 100):
            result = _drive_test_process(
                source,
                io.StringIO(),
                timeout_ms=1_000,
                fail_fast_tool_errors=False,
            )

        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["exit_code"], 124)
        self.assertIn("stagnation", result["error"].lower())

    def test_repeated_denial_with_new_tool_ids_fails_fast(self) -> None:
        source = """
import json
import time
for index in range(10):
    tool_id = f"tool-{index}"
    print(json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "id": tool_id, "input": {"command": "git status --short"}}]}}), flush=True)
    event = {
        "type": "user",
        "message": {
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "is_error": True,
                    "content": "Permission to use Bash has been denied",
                }
            ]
        },
    }
    print(json.dumps(event), flush=True)
    time.sleep(0.04)
time.sleep(2)
"""

        with patch("_executor._MAX_STAGNATION_MS", 100):
            result = _drive_test_process(source, io.StringIO(), timeout_ms=1_000)

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["agent_status"], "BLOCKED")
        self.assertEqual(result["blocker"]["kind"], "permission_denial_loop")

    def test_first_permission_denial_is_terminal_because_grants_cannot_change(self) -> None:
        source = r'''
import json
import time
tool_id = "bash-1"
command = "git status --short && head -20 owned.py"
print(json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "id": tool_id, "input": {"command": command}}]}}), flush=True)
print(json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": tool_id, "is_error": True, "content": "Permission to use Bash has been denied"}]}}), flush=True)
time.sleep(2)
'''
        started_at = time.monotonic()

        result = _drive_test_process(
            source,
            io.StringIO(),
            timeout_ms=2_000,
            semantic_timeout_ms=2_000,
            allowed_commands=("git status --short",),
        )

        self.assertLess(time.monotonic() - started_at, 1.0)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["agent_status"], "BLOCKED")
        self.assertEqual(result["blocker"]["kind"], "permission_denial_loop")
        self.assertEqual(result["blocker"]["occurrences"], 1)
        self.assertEqual(result["blocker"]["grant_match"], "command_not_authorized")

    def test_os_permission_error_from_granted_command_is_not_a_grant_denial(self) -> None:
        source = r'''
import json
tool_id = "bash-1"
command = "pytest -q tests/test_widget.py"
print(json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "id": tool_id, "input": {"command": command}}]}}), flush=True)
print(json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": tool_id, "is_error": True, "content": "OSError: [Errno 13] Permission denied: /tmp/test-artifact"}]}}), flush=True)
print(json.dumps({"type": "result", "result": "diagnosed and fixed"}), flush=True)
'''

        result = _drive_test_process(
            source,
            io.StringIO(),
            timeout_ms=1_000,
            semantic_timeout_ms=1_000,
            allowed_commands=("pytest -q tests/test_widget.py",),
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["result"], "diagnosed and fixed")

    def test_application_permission_errors_are_not_grant_denials(self) -> None:
        errors = (
            "HTTP 403: this API operation requires permission admin.read",
            "You need permission to use /dev/video0",
        )
        for index, error in enumerate(errors):
            with self.subTest(error=error):
                tool_id = f"bash-{index}"
                command = "pytest -q tests/test_widget.py"
                source = _event_source(
                    [
                        {
                            "type": "assistant",
                            "message": {
                                "content": [
                                    {
                                        "type": "tool_use",
                                        "name": "Bash",
                                        "id": tool_id,
                                        "input": {"command": command},
                                    }
                                ]
                            },
                        },
                        {
                            "type": "user",
                            "message": {
                                "content": [
                                    {
                                        "type": "tool_result",
                                        "tool_use_id": tool_id,
                                        "is_error": True,
                                        "content": error,
                                    }
                                ]
                            },
                        },
                        {"type": "result", "result": "diagnosed and fixed"},
                    ]
                )

                result = _drive_test_process(
                    source,
                    io.StringIO(),
                    timeout_ms=1_000,
                    semantic_timeout_ms=1_000,
                    allowed_commands=(command,),
                )

                self.assertEqual(result["status"], "success")
                self.assertEqual(result["result"], "diagnosed and fixed")

    def test_first_permission_denial_reports_grant_mismatch(self) -> None:
        source = r'''
import json
import time
command = "git commit -m 'test: replay proof'"
tool_id = "tool-0"
print(json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "id": tool_id, "input": {"command": command}}]}}), flush=True)
error = f"Permission to use Bash with command {command} has been denied"
print(json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": tool_id, "is_error": True, "content": error}]}}), flush=True)
time.sleep(2)
'''
        started_at = time.monotonic()

        result = _drive_test_process(
            source,
            io.StringIO(),
            timeout_ms=2_000,
            semantic_timeout_ms=2_000,
            allowed_commands=('git commit -m "test: replay proof"',),
        )

        self.assertLess(time.monotonic() - started_at, 1.0)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["agent_status"], "BLOCKED")
        self.assertEqual(result["blocker"]["kind"], "permission_denial_loop")
        self.assertEqual(result["blocker"]["occurrences"], 1)
        self.assertEqual(
            result["blocker"]["grant_match"],
            "argv_equivalent_exact_string_mismatch",
        )
        self.assertIn("git commit", result["blocker"]["attempted_command"])
        self.assertIn("has been denied", result["blocker"]["tool_error"])
        self.assertIn("grant mismatch", result["error"].lower())

    def test_successful_reads_do_not_clear_repeated_bash_denials(self) -> None:
        source = r'''
import json
import time
for index in range(3):
    bash_id = f"bash-{index}"
    print(json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "id": bash_id, "input": {"command": "git commit -m 'replay proof'"}}]}}), flush=True)
    print(json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": bash_id, "is_error": True, "content": "Permission to use Bash has been denied"}]}}), flush=True)
    read_id = f"read-{index}"
    print(json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Read", "id": read_id, "input": {"file_path": "owned.py"}}]}}), flush=True)
    print(json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": read_id, "content": "contents"}]}}), flush=True)
    time.sleep(0.02)
time.sleep(2)
'''

        result = _drive_test_process(
            source,
            io.StringIO(),
            timeout_ms=2_000,
            semantic_timeout_ms=2_000,
            allowed_commands=('git commit -m "replay proof"',),
        )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["agent_status"], "BLOCKED")
        self.assertEqual(result["blocker"]["kind"], "permission_denial_loop")
        self.assertEqual(result["blocker"]["occurrences"], 1)

    def test_later_success_cannot_rescue_a_permission_denial(self) -> None:
        source = r'''
import json
events = [
    ("bash-1", True, "git status --short"),
    ("bash-2", False, "git status --short"),
    ("bash-3", True, "git commit -m 'replay proof'"),
    ("bash-4", True, "git commit -m 'replay proof'"),
]
for tool_id, denied, command in events:
    print(json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "id": tool_id, "input": {"command": command}}]}}), flush=True)
    result = {"type": "tool_result", "tool_use_id": tool_id, "content": "ok"}
    if denied:
        result.update({"is_error": True, "content": "Permission to use Bash has been denied"})
    print(json.dumps({"type": "user", "message": {"content": [result]}}), flush=True)
print(json.dumps({"type": "result", "result": "DONE"}), flush=True)
'''

        result = _drive_test_process(
            source,
            io.StringIO(),
            timeout_ms=1_000,
            semantic_timeout_ms=1_000,
            allowed_commands=("git status --short",),
        )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["agent_status"], "BLOCKED")
        self.assertEqual(result["blocker"]["occurrences"], 1)

    def test_successful_different_bash_command_does_not_clear_denied_commit(self) -> None:
        source = r'''
import json
import time
for index in range(3):
    commit_id = f"commit-{index}"
    commit = "git commit -m 'replay proof'"
    print(json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "id": commit_id, "input": {"command": commit}}]}}), flush=True)
    print(json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": commit_id, "is_error": True, "content": "Permission to use Bash has been denied"}]}}), flush=True)
    status_id = f"status-{index}"
    print(json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "id": status_id, "input": {"command": "git status --short"}}]}}), flush=True)
    print(json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": status_id, "content": "clean"}]}}), flush=True)
    time.sleep(0.02)
time.sleep(2)
'''

        result = _drive_test_process(
            source,
            io.StringIO(),
            timeout_ms=2_000,
            semantic_timeout_ms=2_000,
            allowed_commands=("git status --short", 'git commit -m "replay proof"'),
        )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["agent_status"], "BLOCKED")
        self.assertEqual(result["blocker"]["kind"], "permission_denial_loop")
        self.assertEqual(result["blocker"]["occurrences"], 1)

    def test_repeated_equivalent_tool_error_fails_fast(self) -> None:
        source = r'''
import json
import time
for index in range(3):
    tool_id = f"tool-{index}"
    print(json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Edit", "id": tool_id, "input": {"file_path": "owned.py"}}]}}), flush=True)
    print(json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": tool_id, "is_error": True, "content": "Target changed since it was read"}]}}), flush=True)
    time.sleep(0.02)
time.sleep(2)
'''

        result = _drive_test_process(
            source,
            io.StringIO(),
            timeout_ms=2_000,
            semantic_timeout_ms=2_000,
        )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["agent_status"], "BLOCKED")
        self.assertEqual(result["blocker"]["kind"], "repeated_tool_error")
        self.assertEqual(result["blocker"]["occurrences"], 3)

    def test_exact_grant_denial_is_not_misreported_as_quoting_mismatch(self) -> None:
        source = r'''
import json
tool_id = "tool-0"
print(json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "id": tool_id, "input": {"command": "git status --short"}}]}}), flush=True)
print(json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": tool_id, "is_error": True, "content": "Permission to use Bash has been denied"}]}}), flush=True)
'''

        result = _drive_test_process(
            source,
            io.StringIO(),
            timeout_ms=1_000,
            semantic_timeout_ms=1_000,
            allowed_commands=("git status --short",),
        )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["blocker"]["occurrences"], 1)
        self.assertEqual(result["blocker"]["grant_match"], "exact_grant_present")
        self.assertIn("exact granted command", result["error"])
        self.assertNotIn("grant mismatch", result["error"])

    def test_single_tool_error_is_not_misclassified_as_loop(self) -> None:
        source = r'''
import json
print(json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Edit", "id": "tool-1", "input": {"file_path": "owned.py"}}]}}), flush=True)
print(json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "tool-1", "is_error": True, "content": "Target changed since it was read"}]}}), flush=True)
print(json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Read", "id": "tool-2", "input": {"file_path": "owned.py"}}]}}), flush=True)
print(json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "tool-2", "content": "fresh contents"}]}}), flush=True)
print(json.dumps({"type": "result", "result": "DONE"}), flush=True)
'''

        result = _drive_test_process(
            source,
            io.StringIO(),
            timeout_ms=1_000,
            semantic_timeout_ms=1_000,
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["result"], "DONE")
        self.assertNotIn("blocker", result)

    def test_transport_timeout_does_not_shorten_stagnation_deadline(self) -> None:
        source = """
import json
import time
event = {
    "type": "user",
    "message": {
        "content": [
            {"type": "tool_result", "tool_use_id": "tool-1", "content": "unchanged"}
        ]
    },
}
for _ in range(5):
    print(json.dumps(event), flush=True)
    time.sleep(0.04)
print(json.dumps({"type": "result", "result": "DONE"}), flush=True)
"""

        with patch("_executor._MAX_STAGNATION_MS", 500):
            result = _drive_test_process(source, io.StringIO(), timeout_ms=100)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["result"], "DONE")

    def test_distinct_tool_results_extend_stagnation_deadline(self) -> None:
        source = """
import json
import time
for index in range(5):
    event = {
        "type": "user",
        "message": {
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": f"tool-{index}",
                    "content": f"step {index} complete",
                }
            ]
        },
    }
    print(json.dumps(event), flush=True)
    time.sleep(0.06)
print(json.dumps({"type": "result", "result": "DONE"}), flush=True)
"""

        with patch("_executor._MAX_STAGNATION_MS", 100):
            result = _drive_test_process(source, io.StringIO(), timeout_ms=1_000)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["result"], "DONE")

    def test_non_claude_backend_ignores_semantic_stagnation(self) -> None:
        source = """
import json
import time
for _ in range(5):
    print(json.dumps({"type": "system", "status": "unchanged"}), flush=True)
    time.sleep(0.06)
print(json.dumps({"type": "turn.completed"}), flush=True)
"""

        with patch("_executor._MAX_STAGNATION_MS", 100):
            result = _drive_test_process(
                source,
                io.StringIO(),
                cli="codex",
                timeout_ms=1_000,
            )

        self.assertEqual(result["status"], "success")

    def test_writer_can_finish_long_running_tool_without_semantic_events(self) -> None:
        source = """
import json
import time
print(json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "id": "tool-1", "input": {"command": "pytest"}}]}}), flush=True)
time.sleep(0.2)
print(json.dumps({"type": "result", "result": "DONE"}), flush=True)
"""

        with patch("_executor._MAX_STAGNATION_MS", 50):
            result = _drive_test_process(
                source,
                io.StringIO(),
                timeout_ms=1_000,
                semantic_timeout_ms=1_000,
            )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["result"], "DONE")

    def test_abnormal_cli_signal_cannot_report_transport_success(self) -> None:
        result = build_final_response(
            "minimax",
            143,
            {"type": "result", "status": "success", "result": "DONE"},
            [],
            "",
            terminated_by_us=False,
        )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["transport_exit_code"], 1)
        self.assertEqual(result["exit_code"], 143)
        self.assertEqual(result["cli_exit_code"], 143)
        self.assertEqual(result["termination_reason"], "cli_signal")

    def test_zero_cli_exit_without_terminal_result_is_not_reported_as_cli_exit_one(
        self,
    ) -> None:
        result = build_final_response(
            "minimax",
            0,
            None,
            ["unparseable provider output\n"],
            "",
            terminated_by_us=False,
        )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["transport_exit_code"], 1)
        self.assertEqual(result["exit_code"], 1)
        self.assertEqual(result["cli_exit_code"], 0)
        self.assertEqual(result["termination_reason"], "missing_terminal_result")
        self.assertEqual(
            result["error"],
            "CLI exited with code 0 without a usable terminal result",
        )

    def test_clean_dialogue_exit_promotes_final_assistant_envelope(self) -> None:
        report = (
            "Read-only findings.\n"
            '<subagent_result>{"status":"DONE_WITH_CONCERNS",'
            '"summary":"Mapped the lifecycle","questions":[],"state_file":null,'
            '"concerns":["Parent verification required"]}</subagent_result>'
        )
        source = f"""
import json
print(json.dumps({{
    "type": "assistant",
    "message": {{"content": [{{"type": "text", "text": {report!r}}}]}}
}}), flush=True)
"""

        result = _drive_test_process(
            source,
            io.StringIO(),
            timeout_ms=1_000,
            allow_dialogue_fallback=True,
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["transport_exit_code"], 0)
        self.assertEqual(result["cli_exit_code"], 0)
        self.assertEqual(result["termination_reason"], "assistant_envelope")
        self.assertEqual(result["result"], report)

    def test_structured_output_result_is_a_usable_terminal_event(self) -> None:
        structured_output = {
            "status": "DONE",
            "summary": "Mapped the lifecycle",
            "result": "Detailed findings.",
            "questions": [],
            "state_file": None,
            "concerns": [],
        }
        source = f"""
import json
print(json.dumps({{
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "structured_output": {structured_output!r}
}}), flush=True)
"""

        result = _drive_test_process(
            source,
            io.StringIO(),
            timeout_ms=1_000,
            allow_structured_output=True,
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["termination_reason"], "cli_exit")
        self.assertEqual(result["structured_output"], structured_output)

    def test_clean_schema_exit_recovers_confirmed_structured_tool_result(self) -> None:
        structured_output = {
            "status": "DONE",
            "summary": "Mapped the lifecycle",
            "result": "Detailed findings.",
            "questions": [],
            "state_file": None,
            "concerns": [],
        }
        result = _drive_test_process(
            _event_source(
                [
                    _structured_tool_use("structured-1", structured_output),
                    _tool_result("structured-1"),
                ]
            ),
            io.StringIO(),
            timeout_ms=1_000,
            allow_structured_output=True,
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["termination_reason"], "structured_tool_result")
        self.assertEqual(result["structured_output"], structured_output)

    def test_structured_tool_recovery_requires_schema_and_successful_tool_result(
        self,
    ) -> None:
        tool_use = _structured_tool_use("structured-1", {"result": "Findings."})
        cases = (
            (False, [tool_use, _tool_result("structured-1")]),
            (True, [tool_use]),
            (True, [tool_use, _tool_result("structured-1", is_error=True)]),
        )

        for allow_structured_output, events in cases:
            with self.subTest(
                allow_structured_output=allow_structured_output,
                events=events,
            ):
                result = _drive_test_process(
                    _event_source(events),
                    io.StringIO(),
                    timeout_ms=1_000,
                    allow_structured_output=allow_structured_output,
                )

                self.assertEqual(result["status"], "error")
                self.assertEqual(
                    result["termination_reason"],
                    "missing_terminal_result",
                )

    def test_structured_tool_recovery_uses_only_latest_confirmed_call(self) -> None:
        first = _structured_tool_use("first", {"result": "first"})
        latest = _structured_tool_use("latest", {"result": "latest"})
        first_success = [first, _tool_result("first")]
        cases = (
            [*first_success, latest],
            [
                *first_success,
                latest,
                _tool_result("latest", is_error=True),
            ],
            [first, latest, _tool_result("first")],
            [
                *first_success,
                latest,
                _tool_result("mismatched"),
            ],
        )

        for events in cases:
            with self.subTest(events=events):
                result = _drive_test_process(
                    _event_source(events),
                    io.StringIO(),
                    timeout_ms=1_000,
                    allow_structured_output=True,
                )

                self.assertEqual(result["status"], "error")
                self.assertEqual(
                    result["termination_reason"],
                    "missing_terminal_result",
                )

    def test_structured_tool_recovery_requires_clean_child_exit(self) -> None:
        events = [
            _structured_tool_use("structured-1", {"result": "confirmed"}),
            _tool_result("structured-1"),
        ]

        result = _drive_test_process(
            _event_source(events, exit_code=2),
            io.StringIO(),
            timeout_ms=1_000,
            allow_structured_output=True,
        )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["cli_exit_code"], 2)
        self.assertEqual(result["termination_reason"], "cli_error")
        self.assertNotIn("structured_output", result)

    def test_latest_structured_call_can_confirm_after_prior_error(self) -> None:
        latest_payload = {"result": "latest"}
        events = [
            _structured_tool_use("first", {"result": "first"}),
            _tool_result("first", is_error=True),
            _structured_tool_use("latest", latest_payload),
            _tool_result("latest"),
        ]

        result = _drive_test_process(
            _event_source(events),
            io.StringIO(),
            timeout_ms=1_000,
            allow_structured_output=True,
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["termination_reason"], "structured_tool_result")
        self.assertEqual(result["structured_output"], latest_payload)

    def test_non_schema_invocations_reject_structured_only_terminal_events(self) -> None:
        source = """
import json
print(json.dumps({
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "structured_output": {"unexpected": True}
}), flush=True)
"""

        for cli in ("claude", "cursor-agent"):
            with self.subTest(cli=cli):
                result = _drive_test_process(
                    source,
                    io.StringIO(),
                    cli=cli,
                    timeout_ms=1_000,
                )

                self.assertEqual(result["status"], "error")
                self.assertEqual(
                    result["termination_reason"],
                    "missing_terminal_result",
                )

    def test_structured_output_retry_exhaustion_is_an_explicit_error(self) -> None:
        result = build_final_response(
            "minimax",
            0,
            {
                "type": "result",
                "subtype": "error_max_structured_output_retries",
                "is_error": True,
                "status": "error",
            },
            [],
            "",
        )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["transport_exit_code"], 1)
        self.assertEqual(result["termination_reason"], "cli_exit")
        self.assertEqual(
            result["error"],
            "CLI reported error_max_structured_output_retries",
        )

    def test_clean_non_dialogue_exit_keeps_missing_terminal_error(self) -> None:
        report = (
            "Read-only findings.\n"
            '<subagent_result>{"status":"DONE","summary":"Mapped",'
            '"questions":[],"state_file":null,"concerns":[]}</subagent_result>'
        )
        source = f"""
import json
print(json.dumps({{
    "type": "assistant",
    "message": {{"content": [{{"type": "text", "text": {report!r}}}]}}
}}), flush=True)
"""

        result = _drive_test_process(source, io.StringIO(), timeout_ms=1_000)

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["termination_reason"], "missing_terminal_result")

    def test_dialogue_fallback_rejects_plain_assistant_text(self) -> None:
        source = """
import json
print(json.dumps({
    "type": "assistant",
    "message": {"content": [{"type": "text", "text": "Looks complete."}]}
}), flush=True)
"""

        result = _drive_test_process(
            source,
            io.StringIO(),
            timeout_ms=1_000,
            allow_dialogue_fallback=True,
        )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["termination_reason"], "missing_terminal_result")

    def test_claude_success_subtype_with_zero_exit_is_transport_success(self) -> None:
        report = (
            "Read-only findings.\n"
            '<subagent_result>{"status":"DONE_WITH_CONCERNS",'
            '"summary":"Mapped the lifecycle","questions":[],"state_file":null,'
            '"concerns":["Parent verification required"]}</subagent_result>'
        )
        result = build_final_response(
            "minimax",
            0,
            {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "result": report,
            },
            [],
            "",
            terminated_by_us=False,
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["transport_exit_code"], 0)
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["cli_exit_code"], 0)
        self.assertEqual(result["termination_reason"], "cli_exit")
        self.assertEqual(result["result"], report)

    def test_terminal_event_followed_by_cli_exit_143_is_not_runner_success(self) -> None:
        source = r'''
import json
import os
print(json.dumps({"type": "result", "status": "success", "result": "DONE"}), flush=True)
os._exit(143)
'''

        result = _drive_test_process(
            source,
            io.StringIO(),
            timeout_ms=1_000,
            semantic_timeout_ms=1_000,
        )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["transport_exit_code"], 1)
        self.assertEqual(result["exit_code"], 143)
        self.assertEqual(result["cli_exit_code"], 143)
        self.assertEqual(result["termination_reason"], "cli_signal")

    def test_runner_terminal_signal_is_explicit_and_normalized(self) -> None:
        result = build_final_response(
            "minimax",
            -signal.SIGTERM,
            {"type": "result", "status": "success", "result": "DONE"},
            [],
            "",
            terminated_by_us=True,
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["transport_exit_code"], 0)
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["cli_exit_code"], -signal.SIGTERM)
        self.assertEqual(result["termination_reason"], "terminal_event")

    def test_timeout_kills_the_entire_process_group(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            pid_path = Path(temp_dir) / "grandchild.pid"
            source = f"""
import json
import subprocess
import sys
import time
child = subprocess.Popen(
    [sys.executable, "-c", "import time; time.sleep(60)"],
    stdin=subprocess.DEVNULL,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
open({str(pid_path)!r}, "w", encoding="utf-8").write(str(child.pid))
print(json.dumps({{"type": "system", "session_id": "session-tree"}}), flush=True)
time.sleep(60)
"""

            result = _spawn_and_drive(
                sys.executable,
                ["-u", "-c", source],
                None,
                temp_dir,
                "claude",
                timeout_ms=100,
                heartbeat_sec=0.02,
                progress_stream=io.StringIO(),
            )
            grandchild_pid = int(pid_path.read_text(encoding="utf-8"))

            try:
                deadline = time.monotonic() + 1
                while time.monotonic() < deadline:
                    try:
                        os.kill(grandchild_pid, 0)
                    except ProcessLookupError:
                        break
                    time.sleep(0.02)
                else:
                    self.fail("grandchild process survived runner timeout")
            finally:
                try:
                    os.kill(grandchild_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

            self.assertIn(result["status"], {"partial", "error"})
            self.assertEqual(result["exit_code"], 124)

    def test_timeout_kills_process_group_after_leader_exits(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            pid_path = Path(temp_dir) / "grandchild.pid"
            source = f"""
import json
import subprocess
import sys
child = subprocess.Popen(
    [sys.executable, "-c", "import time; time.sleep(2)"],
)
open({str(pid_path)!r}, "w", encoding="utf-8").write(str(child.pid))
print(json.dumps({{"type": "system", "session_id": "leader-exited"}}), flush=True)
"""

            started_at = time.monotonic()
            result = _spawn_and_drive(
                sys.executable,
                ["-u", "-c", source],
                None,
                temp_dir,
                "claude",
                timeout_ms=100,
                heartbeat_sec=0.02,
                progress_stream=io.StringIO(),
            )
            elapsed = time.monotonic() - started_at
            grandchild_pid = int(pid_path.read_text(encoding="utf-8"))

            try:
                deadline = time.monotonic() + 1
                while time.monotonic() < deadline:
                    try:
                        os.kill(grandchild_pid, 0)
                    except ProcessLookupError:
                        break
                    time.sleep(0.02)
                else:
                    self.fail("grandchild survived after the process leader exited")
            finally:
                try:
                    os.kill(grandchild_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

            self.assertLess(elapsed, 1.0)
            self.assertEqual(result["exit_code"], 124)

    def test_output_limit_kills_the_entire_process_group(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            pid_path = Path(temp_dir) / "grandchild.pid"
            source = f"""
import subprocess
import sys
import time
child = subprocess.Popen(
    [sys.executable, "-c", "import time; time.sleep(60)"],
    stdin=subprocess.DEVNULL,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
open({str(pid_path)!r}, "w", encoding="utf-8").write(str(child.pid))
print("x" * 256, flush=True)
time.sleep(60)
"""

            result = _spawn_and_drive(
                sys.executable,
                ["-u", "-c", source],
                None,
                temp_dir,
                "claude",
                timeout_ms=1_000,
                heartbeat_sec=0.02,
                progress_stream=io.StringIO(),
                max_stdout_chars=64,
            )
            grandchild_pid = int(pid_path.read_text(encoding="utf-8"))

            try:
                deadline = time.monotonic() + 1
                while time.monotonic() < deadline:
                    try:
                        os.kill(grandchild_pid, 0)
                    except ProcessLookupError:
                        break
                    time.sleep(0.02)
                else:
                    self.fail("grandchild process survived output-limit termination")
            finally:
                try:
                    os.kill(grandchild_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

            self.assertEqual(result["status"], "error")
            self.assertIn("output exceeded", result["error"])


if __name__ == "__main__":
    unittest.main()
