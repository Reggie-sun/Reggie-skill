from __future__ import annotations

import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from run_subagent import main  # noqa: E402


def _writer_definition(directory: Path) -> Path:
    definition = directory / "writer.md"
    definition.write_text(
        """---
run-agent: minimax
permission: safe-edit
---

# Writer

Bounded writer.
""",
        encoding="utf-8",
    )
    return definition


def _readonly_definition(directory: Path) -> Path:
    definition = directory / "explorer.md"
    definition.write_text(
        """---
run-agent: minimax
permission: read-only
---

# Explorer

Read only.
""",
        encoding="utf-8",
    )
    return definition


class TddCliContractTests(unittest.TestCase):
    def test_tdd_command_without_tdd_is_rejected_before_backend_start(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            agents_dir = Path(temp_dir) / "agents"
            agents_dir.mkdir()
            _writer_definition(agents_dir)
            command = "pytest -q test_feature.py"
            argv = [
                "run_subagent.py",
                "--agent",
                "writer",
                "--agents-dir",
                str(agents_dir),
                "--cwd",
                temp_dir,
                "--prompt",
                "Fix the behavior",
                "--allow-path",
                "feature.py",
                "--allow-command",
                command,
                "--tdd-command",
                command,
            ]
            stdout = StringIO()

            with (
                patch.object(sys, "argv", argv),
                patch("run_subagent.resolve_cli", return_value="minimax"),
                patch("run_subagent.execute_agent") as execute,
                redirect_stdout(stdout),
                self.assertRaises(SystemExit) as exited,
            ):
                main()

        self.assertEqual(exited.exception.code, 1)
        self.assertFalse(execute.called)
        self.assertIn("--tdd-command requires --tdd", stdout.getvalue())

    def test_tdd_requires_an_exact_verification_command_before_backend_start(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            agents_dir = Path(temp_dir) / "agents"
            agents_dir.mkdir()
            _writer_definition(agents_dir)
            argv = [
                "run_subagent.py",
                "--agent",
                "writer",
                "--agents-dir",
                str(agents_dir),
                "--cwd",
                temp_dir,
                "--prompt",
                "Fix the behavior",
                "--allow-path",
                "feature.py",
                "--allow-path",
                "test_feature.py",
                "--tdd",
            ]
            stdout = StringIO()

            with (
                patch.object(sys, "argv", argv),
                patch("run_subagent.resolve_cli", return_value="minimax"),
                patch("run_subagent.execute_agent") as execute,
                redirect_stdout(stdout),
                self.assertRaises(SystemExit) as exited,
            ):
                main()

        self.assertEqual(exited.exception.code, 1)
        self.assertFalse(execute.called)
        self.assertIn("--tdd requires exactly one --tdd-command", stdout.getvalue())

    def test_tdd_command_must_have_an_identical_allow_command_grant(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            agents_dir = Path(temp_dir) / "agents"
            agents_dir.mkdir()
            _writer_definition(agents_dir)
            argv = [
                "run_subagent.py",
                "--agent",
                "writer",
                "--agents-dir",
                str(agents_dir),
                "--cwd",
                temp_dir,
                "--prompt",
                "Fix the behavior",
                "--allow-path",
                "feature.py",
                "--allow-path",
                "test_feature.py",
                "--allow-command",
                "pytest -q test_other.py",
                "--tdd-command",
                "pytest -q test_feature.py",
                "--tdd",
            ]
            stdout = StringIO()

            with (
                patch.object(sys, "argv", argv),
                patch("run_subagent.resolve_cli", return_value="minimax"),
                patch("run_subagent.execute_agent") as execute,
                redirect_stdout(stdout),
                self.assertRaises(SystemExit) as exited,
            ):
                main()

        self.assertEqual(exited.exception.code, 1)
        self.assertFalse(execute.called)
        self.assertIn("identical --allow-command", stdout.getvalue())

    def test_tdd_rejects_multiple_commands_before_backend_start(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            agents_dir = Path(temp_dir) / "agents"
            agents_dir.mkdir()
            _writer_definition(agents_dir)
            first = "pytest -q test_feature.py"
            second = "pytest -q test_other.py"
            argv = [
                "run_subagent.py",
                "--agent",
                "writer",
                "--agents-dir",
                str(agents_dir),
                "--cwd",
                temp_dir,
                "--prompt",
                "Fix the behavior",
                "--allow-path",
                "feature.py",
                "--allow-command",
                first,
                "--allow-command",
                second,
                "--tdd-command",
                first,
                "--tdd-command",
                second,
                "--tdd",
            ]
            stdout = StringIO()

            with (
                patch.object(sys, "argv", argv),
                patch("run_subagent.resolve_cli", return_value="minimax"),
                patch("run_subagent.execute_agent") as execute,
                redirect_stdout(stdout),
                self.assertRaises(SystemExit) as exited,
            ):
                main()

        self.assertEqual(exited.exception.code, 1)
        self.assertFalse(execute.called)
        self.assertIn("exactly one --tdd-command", stdout.getvalue())

    def test_tdd_requires_safe_edit_before_backend_start(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            agents_dir = Path(temp_dir) / "agents"
            agents_dir.mkdir()
            _readonly_definition(agents_dir)
            command = "pytest -q test_feature.py"
            argv = [
                "run_subagent.py",
                "--agent",
                "explorer",
                "--agents-dir",
                str(agents_dir),
                "--cwd",
                temp_dir,
                "--prompt",
                "Inspect the behavior",
                "--allow-command",
                command,
                "--tdd-command",
                command,
                "--tdd",
            ]
            stdout = StringIO()

            with (
                patch.object(sys, "argv", argv),
                patch("run_subagent.resolve_cli", return_value="minimax"),
                patch("run_subagent.execute_agent") as execute,
                redirect_stdout(stdout),
                self.assertRaises(SystemExit) as exited,
            ):
                main()

        self.assertEqual(exited.exception.code, 1)
        self.assertFalse(execute.called)
        self.assertIn("requires a safe-edit agent", stdout.getvalue())

    def test_tdd_injects_red_green_contract_and_exact_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            agents_dir = Path(temp_dir) / "agents"
            agents_dir.mkdir()
            _writer_definition(agents_dir)
            command = "pytest -q test_feature.py"
            argv = [
                "run_subagent.py",
                "--agent",
                "writer",
                "--agents-dir",
                str(agents_dir),
                "--cwd",
                temp_dir,
                "--prompt",
                "Fix the behavior",
                "--allow-path",
                "feature.py",
                "--allow-path",
                "test_feature.py",
                "--allow-command",
                command,
                "--tdd-command",
                command,
                "--tdd",
            ]
            stdout = StringIO()

            with (
                patch.object(sys, "argv", argv),
                patch("run_subagent.resolve_cli", return_value="minimax"),
                patch(
                    "run_subagent.execute_agent",
                    return_value={
                        "result": "done",
                        "status": "success",
                        "exit_code": 0,
                        "cli": "minimax",
                    },
                ) as execute,
                redirect_stdout(stdout),
                self.assertRaises(SystemExit) as exited,
            ):
                main()

        self.assertEqual(exited.exception.code, 0)
        context = execute.call_args.args[0].system_context
        self.assertIn("Strict TDD Contract", context)
        self.assertIn("Observe RED before editing production code", context)
        self.assertIn("Do not keep pre-RED production edits", context)
        self.assertIn(command, context)
        self.assertEqual(json.loads(stdout.getvalue())["status"], "success")

    def test_writer_without_tdd_preserves_original_system_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            agents_dir = Path(temp_dir) / "agents"
            agents_dir.mkdir()
            _writer_definition(agents_dir)
            argv = [
                "run_subagent.py",
                "--agent",
                "writer",
                "--agents-dir",
                str(agents_dir),
                "--cwd",
                temp_dir,
                "--prompt",
                "Perform a mechanical edit",
                "--allow-path",
                "feature.py",
            ]
            stdout = StringIO()

            with (
                patch.object(sys, "argv", argv),
                patch("run_subagent.resolve_cli", return_value="minimax"),
                patch(
                    "run_subagent.execute_agent",
                    return_value={
                        "result": "done",
                        "status": "success",
                        "exit_code": 0,
                        "cli": "minimax",
                    },
                ) as execute,
                redirect_stdout(stdout),
                self.assertRaises(SystemExit) as exited,
            ):
                main()

        self.assertEqual(exited.exception.code, 0)
        self.assertNotIn(
            "Strict TDD Contract", execute.call_args.args[0].system_context
        )


if __name__ == "__main__":
    unittest.main()
