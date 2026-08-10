from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from _loader import load_agent  # noqa: E402
from run_subagent import _resolve_timeout  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
