from __future__ import annotations

import io
import json
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

from _executor import _drive_process, _spawn_and_drive  # noqa: E402


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
) -> dict:
    process = _python_process(source)
    try:
        return _drive_process(
            process,
            cli,
            timeout_ms=timeout_ms,
            heartbeat_sec=0.02,
            progress_stream=progress,
        )
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()


class ExecutorLivenessTests(unittest.TestCase):
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
                {"type": "tool_result", "tool_use_id": f"tool-{index}", "content": "ok"}
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
