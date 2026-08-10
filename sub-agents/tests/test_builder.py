from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from _builder import AgentInvocation, build_invocation_args  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
