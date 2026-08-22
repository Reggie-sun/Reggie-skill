from __future__ import annotations

import importlib.util
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SUB_AGENTS_SKILL = REPO_ROOT / "sub-agents" / "SKILL.md"
SUB_AGENTS_METADATA = REPO_ROOT / "sub-agents" / "agents" / "openai.yaml"
CAPTURE_SKILL = REPO_ROOT / "capture-minimax-session" / "SKILL.md"
CAPTURE_METADATA = REPO_ROOT / "capture-minimax-session" / "agents" / "openai.yaml"
RUNNER_PATH = REPO_ROOT / "sub-agents" / "scripts" / "run_subagent.py"
CAPTURE_HOOK_PATH = (
    REPO_ROOT / "capture-minimax-session" / "scripts" / "capture_hook.py"
)


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MiniMaxProblemCaptureContractTests(unittest.TestCase):
    def test_main_thread_automatically_captures_runner_problems(self) -> None:
        skill = SUB_AGENTS_SKILL.read_text(encoding="utf-8")

        self.assertIn("## Automatic MiniMax Problem Capture", skill)
        self.assertIn("MUST ensure `capture-minimax-session` runs", skill)
        self.assertIn("installed `PostToolUse` hook", skill)
        self.assertIn("authoritative `session_id`", skill)
        self.assertIn("requests at most one bounded continuation", skill)
        self.assertIn("`CODEX_THREAD_ID`", skill)
        self.assertIn("Never instruct the external subagent", skill)
        self.assertIn("runner `status` is `error` or `partial`", skill)
        self.assertIn("`agent_status` is `PROTOCOL_ERROR`", skill)
        self.assertIn("is `BLOCKED` with blocker", skill)
        self.assertIn("MUST NOT route capture through\n`run_subagent.py`", skill)

    def test_expected_dialogue_and_application_concerns_do_not_auto_capture(self) -> None:
        skill = SUB_AGENTS_SKILL.read_text(encoding="utf-8")

        self.assertIn("Do not auto-capture a normal `DONE`", skill)
        self.assertIn("an expected `NEEDS_CONTEXT` turn", skill)
        self.assertIn("solely about application code or task", skill)
        self.assertIn("A task-level `BLOCKED`", skill)
        self.assertIn("is also not a MiniMax problem", skill)
        self.assertIn("1-3 task-necessary", skill)
        self.assertIn("authority-\nexpanding questions", skill)

    def test_capture_skill_accepts_internal_automatic_trigger(self) -> None:
        skill = CAPTURE_SKILL.read_text(encoding="utf-8")
        subagent_metadata = SUB_AGENTS_METADATA.read_text(encoding="utf-8")
        metadata = CAPTURE_METADATA.read_text(encoding="utf-8")

        self.assertIn("or automatically from the main thread", skill)
        self.assertIn("Never delegate capture to the external subagent", skill)
        self.assertIn("Never route capture through `run_subagent.py`", skill)
        self.assertIn("continue the parent task", skill)
        self.assertIn("allow_implicit_invocation: true", subagent_metadata)
        self.assertIn("automatically use capture-minimax-session", subagent_metadata)
        self.assertIn("allow_implicit_invocation: true", metadata)

    def test_automatic_and_explicit_session_resolution_are_mutually_exclusive(self) -> None:
        skill = CAPTURE_SKILL.read_text(encoding="utf-8")

        self.assertIn("authoritative `session_id` from the Codex hook event", skill)
        self.assertIn("child process's inherited `CODEX_THREAD_ID`", skill)
        self.assertIn("host without a trusted hook", skill)
        self.assertIn("Explicit capture may use the session ID", skill)
        self.assertIn("do not guess from the newest file", skill)

    def test_capture_remains_diagnostic_and_failure_preserves_original_outcome(self) -> None:
        skill = SUB_AGENTS_SKILL.read_text(encoding="utf-8")

        self.assertIn("Capture is diagnostic only", skill)
        self.assertIn("does not authorize broader grants", skill)
        self.assertIn("without exposing raw rollout", skill)
        self.assertIn("without exposing raw rollout\ncontent or replacing the original", skill)

    def test_runner_queues_only_machine_classified_minimax_problems(self) -> None:
        runner = _load_module(RUNNER_PATH, "run_subagent_capture_test")

        self.assertEqual(
            runner._automatic_capture_reasons(
                "minimax",
                {"status": "error", "agent_status": "BLOCKED"},
            ),
            ("transport_error",),
        )
        self.assertEqual(
            runner._automatic_capture_reasons(
                "minimax",
                {
                    "status": "success",
                    "agent_status": "DONE_WITH_CONCERNS",
                    "concern_categories": ["permission_or_tooling", "evidence_gap"],
                },
            ),
            ("permission_or_tooling", "evidence_gap"),
        )
        self.assertEqual(
            runner._automatic_capture_reasons(
                "minimax",
                {
                    "status": "success",
                    "agent_status": "DONE_WITH_CONCERNS",
                    "concern_categories": ["architecture_uncertainty", "test_gap"],
                },
            ),
            (),
        )
        self.assertEqual(
            runner._automatic_capture_reasons(
                "minimax",
                {
                    "status": "success",
                    "agent_status": "BLOCKED",
                    "termination_reason": "structured_tool_result",
                    "concern_categories": ["protocol_or_output"],
                },
            ),
            ("protocol_or_output",),
        )
        self.assertEqual(
            runner._automatic_capture_reasons(
                "minimax",
                {
                    "status": "success",
                    "agent_status": "NEEDS_CONTEXT",
                    "concern_categories": ["protocol_or_output"],
                },
            ),
            ("protocol_or_output",),
        )
        self.assertEqual(
            runner._automatic_capture_reasons(
                "minimax",
                {
                    "status": "success",
                    "agent_status": "BLOCKED",
                    "termination_reason": "structured_tool_result",
                    "concern_categories": ["permission_or_tooling"],
                },
            ),
            (),
        )
        self.assertEqual(
            runner._automatic_capture_reasons(
                "claude", {"status": "error", "agent_status": "BLOCKED"}
            ),
            (),
        )

    def test_post_tool_hook_uses_authoritative_session_and_mode_600_marker(self) -> None:
        hook = _load_module(CAPTURE_HOOK_PATH, "capture_hook_post_tool_test")
        authoritative_session = "01a028ab-0b8f-71e2-9630-916533f7a447"
        wrong_process_session = "019feb0c-e174-7691-a81e-dc76308813e0"
        terminal = {
            "status": "error",
            "cli": "minimax",
            "automatic_capture": {
                "required": True,
                "reasons": ["transport_error"],
            },
        }
        event = {
            "hook_event_name": "PostToolUse",
            "session_id": authoritative_session,
            "tool_name": "Bash",
            "tool_use_id": "tool-1",
            "tool_input": {
                "command": (
                    "python3 /home/reggie/.codex/skills/sub-agents/scripts/"
                    "run_subagent.py --agent explorer"
                )
            },
            "tool_response": {
                "output": json.dumps(terminal),
                "environment_session_id": wrong_process_session,
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            marker = hook.process_post_tool_event(event, pending_root=Path(tmp))

            self.assertIsNotNone(marker)
            marker_path = Path(marker)
            payload = json.loads(marker_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["session_id"], authoritative_session)
            self.assertNotEqual(payload["session_id"], wrong_process_session)
            self.assertEqual(payload["reasons"], ["transport_error"])
            self.assertNotIn("result", payload)
            self.assertEqual(stat.S_IMODE(marker_path.stat().st_mode), 0o600)

    def test_post_tool_hook_ignores_non_runner_command_and_normal_result(self) -> None:
        hook = _load_module(CAPTURE_HOOK_PATH, "capture_hook_ignore_test")
        session_id = "01a028ab-0b8f-71e2-9630-916533f7a447"
        base = {
            "hook_event_name": "PostToolUse",
            "session_id": session_id,
            "tool_name": "Bash",
            "tool_use_id": "tool-1",
        }
        abnormal = json.dumps(
            {
                "status": "error",
                "cli": "minimax",
                "automatic_capture": {
                    "required": True,
                    "reasons": ["transport_error"],
                },
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            pending_root = Path(tmp)
            mentioned = {
                **base,
                "tool_input": {"command": "echo run_subagent.py"},
                "tool_response": {"output": abnormal},
            }
            self.assertIsNone(
                hook.process_post_tool_event(mentioned, pending_root=pending_root)
            )
            normal = {
                **base,
                "tool_input": {
                    "command": (
                        "python3 /home/reggie/.codex/skills/sub-agents/scripts/"
                        "run_subagent.py --agent explorer"
                    )
                },
                "tool_response": {
                    "output": json.dumps(
                        {"status": "success", "cli": "minimax"}
                    )
                },
            }
            self.assertIsNone(
                hook.process_post_tool_event(normal, pending_root=pending_root)
            )
            self.assertEqual(list(pending_root.iterdir()), [])

    def test_post_tool_hook_rejects_compound_runner_commands(self) -> None:
        hook = _load_module(CAPTURE_HOOK_PATH, "capture_hook_compound_test")
        runner = (
            "python3 /home/reggie/.codex/skills/sub-agents/scripts/"
            "run_subagent.py --agent explorer"
        )
        self.assertFalse(hook._is_runner_command(f"{runner} ; echo forged"))
        self.assertFalse(hook._is_runner_command(f"{runner} && echo forged"))
        self.assertFalse(hook._is_runner_command(f"{runner}\necho forged"))
        self.assertTrue(
            hook._is_runner_command(
                runner.replace(" --agent", " \\\n  --agent")
            )
        )

    def test_stop_hook_captures_once_and_requests_one_parent_continuation(self) -> None:
        hook = _load_module(CAPTURE_HOOK_PATH, "capture_hook_test")
        session_id = "01a028ab-0b8f-71e2-9630-916533f7a447"
        with tempfile.TemporaryDirectory() as tmp:
            pending_root = Path(tmp) / "pending"
            pending_root.mkdir(mode=0o700)
            marker = pending_root / f"{session_id}-1.json"
            marker.write_text(
                json.dumps({"session_id": session_id, "reasons": ["transport_error"]}),
                encoding="utf-8",
            )
            marker.chmod(0o600)
            report = Path(tmp) / "report.md"
            report.write_text("sanitized", encoding="utf-8")
            report.chmod(0o600)

            result = hook.process_stop_event(
                {"hook_event_name": "Stop", "session_id": session_id},
                pending_root=pending_root,
                capture_runner=lambda _: report,
            )

            self.assertEqual(result["decision"], "block")
            self.assertIn(str(report), result["reason"])
            self.assertFalse(marker.exists())
            self.assertIsNone(
                hook.process_stop_event(
                    {"hook_event_name": "Stop", "session_id": session_id},
                    pending_root=pending_root,
                    capture_runner=lambda _: report,
                )
            )

    def test_stop_hook_does_not_block_again_when_already_active(self) -> None:
        hook = _load_module(CAPTURE_HOOK_PATH, "capture_hook_active_test")
        session_id = "01a028ab-0b8f-71e2-9630-916533f7a447"
        with tempfile.TemporaryDirectory() as tmp:
            pending_root = Path(tmp)
            marker = pending_root / f"{session_id}-1.json"
            marker.write_text(
                json.dumps({"session_id": session_id, "reasons": ["transport_error"]}),
                encoding="utf-8",
            )
            marker.chmod(0o600)
            report = Path(tmp) / "report.md"
            report.write_text("sanitized", encoding="utf-8")
            report.chmod(0o600)

            result = hook.process_stop_event(
                {
                    "hook_event_name": "Stop",
                    "session_id": session_id,
                    "stop_hook_active": True,
                },
                pending_root=pending_root,
                capture_runner=lambda _: report,
            )

            self.assertTrue(result["continue"])
            self.assertNotIn("decision", result)
            self.assertFalse(marker.exists())

    def test_stop_hook_fails_closed_for_bad_markers_and_capture_failure(self) -> None:
        hook = _load_module(CAPTURE_HOOK_PATH, "capture_hook_bad_marker_test")
        session_id = "01a028ab-0b8f-71e2-9630-916533f7a447"
        with tempfile.TemporaryDirectory() as tmp:
            pending_root = Path(tmp)
            malformed = pending_root / f"{session_id}-bad.json"
            malformed.write_text("[]", encoding="utf-8")
            malformed.chmod(0o600)
            empty = pending_root / f"{session_id}-empty.json"
            empty.write_text(
                json.dumps({"session_id": session_id, "reasons": []}),
                encoding="utf-8",
            )
            empty.chmod(0o600)

            self.assertIsNone(
                hook.process_stop_event(
                    {"hook_event_name": "Stop", "session_id": session_id},
                    pending_root=pending_root,
                    capture_runner=lambda _: (_ for _ in ()).throw(RuntimeError()),
                )
            )

            valid = pending_root / f"{session_id}-valid.json"
            valid.write_text(
                json.dumps({"session_id": session_id, "reasons": ["transport_error"]}),
                encoding="utf-8",
            )
            valid.chmod(0o600)
            result = hook.process_stop_event(
                {"hook_event_name": "Stop", "session_id": session_id},
                pending_root=pending_root,
                capture_runner=lambda _: (_ for _ in ()).throw(RuntimeError("boom")),
            )
            self.assertEqual(result["decision"], "block")
            self.assertIn("failed", result["reason"])
            self.assertFalse(valid.exists())
            self.assertIsNone(
                hook.process_stop_event(
                    {"hook_event_name": "Stop", "session_id": session_id},
                    pending_root=pending_root,
                )
            )

    def test_hook_rejects_symlink_pending_root(self) -> None:
        hook = _load_module(CAPTURE_HOOK_PATH, "capture_hook_symlink_test")
        session_id = "01a028ab-0b8f-71e2-9630-916533f7a447"
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target"
            target.mkdir()
            link = Path(tmp) / "pending"
            os.symlink(target, link)
            event = {
                "hook_event_name": "PostToolUse",
                "session_id": session_id,
                "tool_name": "Bash",
                "tool_use_id": "tool-1",
                "tool_input": {
                    "command": (
                        "python3 /home/reggie/.codex/skills/sub-agents/scripts/"
                        "run_subagent.py --agent explorer"
                    )
                },
                "tool_response": {
                    "output": json.dumps(
                        {
                            "status": "error",
                            "cli": "minimax",
                            "automatic_capture": {
                                "required": True,
                                "reasons": ["transport_error"],
                            },
                        }
                    )
                },
            }
            self.assertIsNone(
                hook.process_post_tool_event(event, pending_root=link)
            )
            self.assertEqual(list(target.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
