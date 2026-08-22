from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SUB_AGENTS_SKILL = REPO_ROOT / "sub-agents" / "SKILL.md"
SUB_AGENTS_METADATA = REPO_ROOT / "sub-agents" / "agents" / "openai.yaml"
CAPTURE_SKILL = REPO_ROOT / "capture-minimax-session" / "SKILL.md"
CAPTURE_METADATA = REPO_ROOT / "capture-minimax-session" / "agents" / "openai.yaml"


class MiniMaxProblemCaptureContractTests(unittest.TestCase):
    def test_main_thread_automatically_captures_runner_problems(self) -> None:
        skill = SUB_AGENTS_SKILL.read_text(encoding="utf-8")

        self.assertIn("## Automatic MiniMax Problem Capture", skill)
        self.assertIn("MUST invoke `capture-minimax-session`", skill)
        self.assertIn("`CODEX_THREAD_ID`", skill)
        self.assertIn("never instruct the external subagent", skill)
        self.assertIn("runner `status` is `error` or `partial`", skill)
        self.assertIn("`agent_status` is `PROTOCOL_ERROR`", skill)
        self.assertIn("is `BLOCKED` with blocker", skill)
        self.assertIn("MUST NOT\nroute capture through `run_subagent.py`", skill)

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
        self.assertIn("never delegate capture to the external subagent", skill)
        self.assertIn("Never route capture through `run_subagent.py`", skill)
        self.assertIn("continue the parent task", skill)
        self.assertIn("allow_implicit_invocation: true", subagent_metadata)
        self.assertIn("automatically use capture-minimax-session", subagent_metadata)
        self.assertIn("allow_implicit_invocation: true", metadata)

    def test_automatic_and_explicit_session_resolution_are_mutually_exclusive(self) -> None:
        skill = CAPTURE_SKILL.read_text(encoding="utf-8")

        self.assertIn("Automatic mode MUST use only the current `CODEX_THREAD_ID`", skill)
        self.assertIn("Ignore historical or supplied session IDs", skill)
        self.assertIn("Explicit capture may use the session ID", skill)
        self.assertIn("do not guess from the newest file", skill)

    def test_capture_remains_diagnostic_and_failure_preserves_original_outcome(self) -> None:
        skill = SUB_AGENTS_SKILL.read_text(encoding="utf-8")

        self.assertIn("Capture is diagnostic only", skill)
        self.assertIn("does not authorize broader grants", skill)
        self.assertIn("without exposing raw rollout", skill)
        self.assertIn("without exposing raw rollout\ncontent or replacing the original", skill)


if __name__ == "__main__":
    unittest.main()
