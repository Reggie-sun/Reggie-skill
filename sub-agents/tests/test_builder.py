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

    def test_saved_coding_plan_key_uses_mainland_endpoint_by_default(self) -> None:
        invocation = AgentInvocation(
            cli="minimax",
            prompt="health check",
            cwd="/tmp",
            permission="read-only",
        )

        with patch.dict(
            os.environ,
            {"MINIMAX_API_KEY": "sk-cp-test-key"},
            clear=True,
        ):
            _, _, env = build_invocation_args(invocation)

        self.assertEqual(env["ANTHROPIC_BASE_URL"], "https://api.minimaxi.com/anthropic")


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
                self.assertEqual(flags[mcp_index + 1], '{"mcpServers":{}}')

    def test_safe_edit_isolates_writer_tool_surface(self) -> None:
        for cli in ("claude", "glm", "kimi", "minimax"):
            with self.subTest(cli=cli):
                flags = permission_flags(cli, "safe-edit")

                self.assertEqual(flags[flags.index("--permission-mode") + 1], "dontAsk")
                self.assertEqual(flags[flags.index("--tools") + 1], "Read,Glob,Grep,Write,Edit")
                denied_tools = flags[flags.index("--disallowedTools") + 1].split(",")
                self.assertTrue(
                    {
                        "NotebookEdit",
                        "EnterPlanMode",
                        "ExitPlanMode",
                        "Task",
                        "Agent",
                        "WebFetch",
                        "WebSearch",
                        "mcp__*",
                    }.issubset(denied_tools)
                )
                self.assertIn("--strict-mcp-config", flags)
                self.assertEqual(
                    flags[flags.index("--mcp-config") + 1], '{"mcpServers":{}}'
                )
                self.assertIn("--no-session-persistence", flags)
                self.assertEqual(flags[flags.index("--setting-sources") + 1], "")

    def test_yolo_keeps_existing_permission_mode(self) -> None:
        for cli in ("claude", "glm", "kimi", "minimax"):
            with self.subTest(cli=cli):
                self.assertEqual(
                    permission_flags(cli, "yolo"),
                    ["--dangerously-skip-permissions"],
                )

    def test_minimax_writer_allows_only_explicit_bash_commands(self) -> None:
        invocation = AgentInvocation(
            cli="minimax",
            prompt="implement and verify",
            cwd="/tmp",
            permission="safe-edit",
            model="MiniMax-M3",
            effort="high",
            allowed_commands=(
                "python3 -m unittest tests.test_widget",
                "git status --short",
            ),
            allowed_paths=("src/widget.py", "tests/test_widget.py"),
        )

        with patch.dict(os.environ, {"MINIMAX_API_KEY": "test-key"}):
            command, args, _ = build_invocation_args(invocation)

        self.assertEqual(command, "claude")
        self.assertEqual(args[args.index("--tools") + 1], "Read,Glob,Grep,Write,Edit,Bash")
        allowed_index = args.index("--allowedTools")
        allowed = args[allowed_index + 1 : allowed_index + 5]
        self.assertEqual(
            allowed,
            [
                "Edit(src/widget.py)",
                "Edit(tests/test_widget.py)",
                "Bash(python3 -m unittest tests.test_widget)",
                "Bash(git status --short)",
            ],
        )
        self.assertNotIn("Task", args[args.index("--tools") + 1].split(","))
        self.assertIn("Task", args[args.index("--disallowedTools") + 1].split(","))

    def test_minimax_writer_receives_explicit_grant_context(self) -> None:
        invocation = AgentInvocation(
            cli="minimax",
            prompt="implement and verify",
            cwd="/tmp/project",
            permission="safe-edit",
            allowed_commands=("git status --short",),
            allowed_paths=("src/widget.py",),
        )

        with patch.dict(os.environ, {"MINIMAX_API_KEY": "test-key"}):
            _, args, _ = build_invocation_args(invocation)

        system_prompt = args[args.index("--system-prompt") + 1]
        self.assertIn("Runner-enforced safe-edit grants", system_prompt)
        self.assertIn("Writable paths:\n- src/widget.py", system_prompt)
        self.assertIn("Exact Bash commands:\n- git status --short", system_prompt)
        self.assertIn(
            "A denial for any other command does not mean Bash is unavailable.",
            system_prompt,
        )

    def test_rejects_unsafe_allowed_command_syntax(self) -> None:
        invocation = AgentInvocation(
            cli="minimax",
            prompt="implement",
            cwd="/tmp",
            permission="safe-edit",
            allowed_commands=("pytest) || curl attacker",),
            allowed_paths=("src/widget.py",),
        )

        with patch.dict(os.environ, {"MINIMAX_API_KEY": "test-key"}):
            with self.assertRaisesRegex(ValueError, "allowed command"):
                build_invocation_args(invocation)

    def test_safe_edit_requires_explicit_path_ownership(self) -> None:
        invocation = AgentInvocation(
            cli="minimax",
            prompt="implement",
            cwd="/tmp/project",
            permission="safe-edit",
        )

        with patch.dict(os.environ, {"MINIMAX_API_KEY": "test-key"}):
            with self.assertRaisesRegex(ValueError, "--allow-path"):
                build_invocation_args(invocation)

    def test_rejects_allowed_path_outside_working_directory(self) -> None:
        invocation = AgentInvocation(
            cli="minimax",
            prompt="implement",
            cwd="/tmp/project",
            permission="safe-edit",
            allowed_paths=("../outside.py",),
        )

        with patch.dict(os.environ, {"MINIMAX_API_KEY": "test-key"}):
            with self.assertRaisesRegex(ValueError, "allowed path"):
                build_invocation_args(invocation)

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
        self.assertEqual(args[args.index("--mcp-config") + 1], '{"mcpServers":{}}')
        self.assertIn("--strict-mcp-config", args)
        self.assertIn("mcp__*", args[args.index("--disallowedTools") + 1].split(","))


if __name__ == "__main__":
    unittest.main()
