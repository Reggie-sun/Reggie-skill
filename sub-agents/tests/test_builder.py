from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from _builder import AgentInvocation, build_invocation_args, permission_flags  # noqa: E402


class MiniMaxEffortTests(unittest.TestCase):
    def test_max_effort_is_forwarded_to_claude_transport(self) -> None:
        invocation = AgentInvocation(
            cli="minimax",
            prompt="health check",
            cwd="/tmp",
            permission="read-only",
            model="MiniMax-M3",
            effort="max",
        )

        with patch.dict(os.environ, {"MINIMAX_API_KEY": "test-key"}):
            command, args, _ = build_invocation_args(invocation)

        self.assertEqual(command, "claude")
        effort_index = args.index("--effort")
        self.assertEqual(args[effort_index + 1], "max")


class ClaudeFamilyReadOnlyTests(unittest.TestCase):
    def test_read_only_exposes_only_non_mutating_tools(self) -> None:
        for cli in ("claude", "glm", "kimi", "minimax"):
            with self.subTest(cli=cli):
                flags = permission_flags(cli, "read-only")

                self.assertEqual(flags[flags.index("--permission-mode") + 1], "dontAsk")
                self.assertNotIn("plan", flags)
                self.assertEqual(flags[flags.index("--tools") + 1], "Read,Glob,Grep")
                denied_tools = flags[flags.index("--disallowedTools") + 1].split(",")
                self.assertTrue(
                    {
                        "Write",
                        "Edit",
                        "NotebookEdit",
                        "EnterPlanMode",
                        "ExitPlanMode",
                        "Task",
                        "Bash",
                        "mcp__*",
                    }.issubset(denied_tools)
                )
                self.assertIn("--no-session-persistence", flags)
                settings_index = flags.index("--setting-sources")
                self.assertEqual(flags[settings_index + 1], "")
                self.assertIn("--strict-mcp-config", flags)
                mcp_index = flags.index("--mcp-config")
                self.assertEqual(flags[mcp_index + 1], "{}")

    def test_safe_edit_and_yolo_keep_existing_permission_modes(self) -> None:
        for cli in ("claude", "glm", "kimi", "minimax"):
            with self.subTest(cli=cli):
                self.assertEqual(
                    permission_flags(cli, "safe-edit"),
                    ["--permission-mode", "acceptEdits"],
                )
                self.assertEqual(
                    permission_flags(cli, "yolo"),
                    ["--dangerously-skip-permissions"],
                )

    def test_minimax_final_argv_contains_read_only_isolation(self) -> None:
        invocation = AgentInvocation(
            cli="minimax",
            prompt="inspect only",
            cwd="/tmp",
            permission="read-only",
            model="MiniMax-M3",
            effort="max",
        )

        with patch.dict(os.environ, {"MINIMAX_API_KEY": "test-key"}):
            command, args, _ = build_invocation_args(invocation)

        self.assertEqual(command, "claude")
        self.assertEqual(args[args.index("--permission-mode") + 1], "dontAsk")
        self.assertEqual(args[args.index("--tools") + 1], "Read,Glob,Grep")
        self.assertIn("--mcp-config", args)
        self.assertEqual(args[args.index("--mcp-config") + 1], "{}")
        self.assertIn("--strict-mcp-config", args)
        self.assertIn("mcp__*", args[args.index("--disallowedTools") + 1].split(","))


if __name__ == "__main__":
    unittest.main()
