from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from _loader import (  # noqa: E402
    discover_agents,
    load_agent,
    resolve_agent_reference,
)
from run_subagent import _resolve_timeout, main  # noqa: E402


class AgentTimeoutTests(unittest.TestCase):
    def test_agent_default_timeout_is_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            agent_path = Path(temp_dir) / "writer.md"
            agent_path.write_text(
                """---
run-agent: minimax
timeout: 1800000
---

# Writer

Bounded writer.
""",
                encoding="utf-8",
            )

            *_, timeout_ms = load_agent(temp_dir, "writer")

        self.assertEqual(timeout_ms, 1_800_000)

    def test_cli_timeout_overrides_agent_default(self) -> None:
        self.assertEqual(_resolve_timeout(45_000, 1_800_000), 45_000)

    def test_agent_timeout_precedes_global_default(self) -> None:
        self.assertEqual(_resolve_timeout(None, 1_800_000), 1_800_000)


class AgentReferenceTests(unittest.TestCase):
    def setUp(self) -> None:
        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    def test_absolute_definition_path_resolves_to_directory_and_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            definition = Path(temp_dir) / "writer.md"
            definition.write_text("# Writer\n", encoding="utf-8")

            agents_dir, agent_name = resolve_agent_reference(
                str(definition),
                args_agents_dir=None,
                args_cwd=temp_dir,
                host_agents_dir=str(Path(temp_dir) / "host"),
            )

        self.assertEqual(agents_dir, temp_dir)
        self.assertEqual(agent_name, "writer")

    def test_missing_project_definition_falls_back_to_host_definition(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            workspace.mkdir()
            host = Path(temp_dir) / "host-agents"
            host.mkdir()
            (host / "writer.md").write_text("# Host writer\n", encoding="utf-8")

            agents_dir, agent_name = resolve_agent_reference(
                "writer",
                args_agents_dir=None,
                args_cwd=str(workspace),
                host_agents_dir=str(host),
            )

        self.assertEqual(agents_dir, str(host))
        self.assertEqual(agent_name, "writer")

    def test_project_definition_wins_over_host_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            project_agents = workspace / ".agents"
            project_agents.mkdir(parents=True)
            (project_agents / "writer.md").write_text(
                "# Project writer\n", encoding="utf-8"
            )
            host = Path(temp_dir) / "host-agents"
            host.mkdir()
            (host / "writer.md").write_text("# Host writer\n", encoding="utf-8")

            agents_dir, _ = resolve_agent_reference(
                "writer",
                args_agents_dir=None,
                args_cwd=str(workspace),
                host_agents_dir=str(host),
            )

        self.assertEqual(agents_dir, str(project_agents))

    def test_explicit_agents_directory_does_not_silently_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            explicit = Path(temp_dir) / "explicit"
            explicit.mkdir()
            host = Path(temp_dir) / "host"
            host.mkdir()
            (host / "writer.md").write_text("# Host writer\n", encoding="utf-8")

            agents_dir, agent_name = resolve_agent_reference(
                "writer",
                args_agents_dir=str(explicit),
                args_cwd=temp_dir,
                host_agents_dir=str(host),
            )

        self.assertEqual(agents_dir, str(explicit))
        self.assertEqual(agent_name, "writer")

    def test_sub_agents_dir_environment_does_not_silently_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            explicit = Path(temp_dir) / "explicit"
            explicit.mkdir()
            host = Path(temp_dir) / "host"
            host.mkdir()
            (host / "writer.md").write_text("# Host writer\n", encoding="utf-8")

            with patch.dict(os.environ, {"SUB_AGENTS_DIR": str(explicit)}):
                agents_dir, agent_name = resolve_agent_reference(
                    "writer",
                    args_agents_dir=None,
                    args_cwd=temp_dir,
                    host_agents_dir=str(host),
                )

        self.assertEqual(agents_dir, str(explicit))
        self.assertEqual(agent_name, "writer")

    def test_discovery_merges_project_and_host_with_project_precedence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            project_agents = workspace / ".agents"
            project_agents.mkdir(parents=True)
            (project_agents / "explorer.md").write_text(
                "# Explorer\n\nProject explorer.\n", encoding="utf-8"
            )
            host = Path(temp_dir) / "host"
            host.mkdir()
            (host / "explorer.md").write_text(
                "# Explorer\n\nHost explorer.\n", encoding="utf-8"
            )
            (host / "writer.md").write_text(
                "# Writer\n\nHost writer.\n", encoding="utf-8"
            )

            agents, agents_dir, fallback_dir = discover_agents(
                args_agents_dir=None,
                args_cwd=str(workspace),
                host_agents_dir=str(host),
            )

        self.assertEqual([agent["name"] for agent in agents], ["explorer", "writer"])
        self.assertEqual(agents[0]["description"], "Project explorer.")
        self.assertEqual(agents_dir, str(project_agents))
        self.assertEqual(fallback_dir, str(host))

    def test_main_accepts_absolute_definition_path_before_backend_start(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            definition = Path(temp_dir) / "writer.md"
            definition.write_text(
                "---\nrun-agent: minimax\npermission: safe-edit\n---\n# Writer\n",
                encoding="utf-8",
            )
            argv = [
                "run_subagent.py",
                "--agent",
                str(definition),
                "--cwd",
                temp_dir,
                "--prompt",
                "Implement the task",
                "--allow-path",
                "owned.py",
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
        self.assertEqual(execute.call_args.args[0].agent_file, str(definition))
        self.assertEqual(json.loads(stdout.getvalue())["status"], "success")

    def test_main_falls_back_to_host_definition_by_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            workspace.mkdir()
            host = Path(temp_dir) / "host"
            host.mkdir()
            definition = host / "writer.md"
            definition.write_text(
                "---\nrun-agent: minimax\npermission: safe-edit\n---\n# Writer\n",
                encoding="utf-8",
            )
            argv = [
                "run_subagent.py",
                "--agent",
                "writer",
                "--cwd",
                str(workspace),
                "--prompt",
                "Implement the task",
                "--allow-path",
                "owned.py",
            ]
            stdout = StringIO()

            with (
                patch.dict(os.environ, {"SUB_AGENTS_HOST_DIR": str(host)}),
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
        self.assertEqual(execute.call_args.args[0].agent_file, str(definition))
        self.assertEqual(json.loads(stdout.getvalue())["status"], "success")


if __name__ == "__main__":
    unittest.main()
