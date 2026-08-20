from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).parents[1] / "scripts" / "capture_session.py"
SPEC = importlib.util.spec_from_file_location("capture_session", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _write_rollout(path: Path, session_id: str) -> None:
    records = [
        {
            "timestamp": "2026-08-19T00:00:00Z",
            "type": "session_meta",
            "payload": {"id": session_id, "cwd": "/repo"},
        },
        {
            "timestamp": "2026-08-19T00:01:00Z",
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call",
                "call_id": "runner-call",
                "name": "exec",
                "input": (
                    'const r = await tools.exec_command({cmd:"python3 '
                    '/skills/sub-agents/scripts/run_subagent.py --agent explorer '
                    '--cwd /repo --dialogue --require-evidence-path owner.py '
                    '--allow-command \\\"pytest -q\\\" --prompt \\\"secret task text\\\""});'
                ),
            },
        },
        {
            "timestamp": "2026-08-19T00:02:00Z",
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call_output",
                "call_id": "runner-call",
                "output": {
                    "wall_time_seconds": 1.0,
                    "exit_code": 1,
                    "output": (
                        "[sub-agent] activity cli=minimax elapsed=4s event=tool:Read "
                        "session=external-1\n"
                        + json.dumps(
                        {
                            "cli": "minimax",
                            "status": "error",
                            "exit_code": 1,
                            "transport_exit_code": 1,
                            "cli_exit_code": 0,
                            "termination_reason": "evidence_incomplete",
                            "agent_status": "BLOCKED",
                            "observed_evidence_paths": [],
                            "concerns": [],
                            "concern_categories": ["permission_or_tooling"],
                            "evidence_categories": ["files_inspected"],
                            "runner_context": {
                                "model": "MiniMax-M3",
                                "effort": "high",
                                "permission": "read-only",
                                "tools_mode": "explicit",
                                "tools": ["Read", "Glob", "Grep", "StructuredOutput"],
                            },
                            "error": (
                                "Permission denied: env PRIVATE_VALUE=hunter2 curl "
                                "https://example.test -H 'Authorization: ghp_abcdefghijklmnop' "
                                "evidence_incomplete"
                            ),
                            "blocker": {"kind": "missing_required_evidence"},
                        }
                        )
                    ),
                },
            },
        },
    ]
    path.write_text("".join(json.dumps(item) + "\n" for item in records), encoding="utf-8")


class CaptureSessionTests(unittest.TestCase):
    def test_quoted_cmd_runner_input_is_parsed_but_list_is_not_an_invocation(self) -> None:
        timestamp = "2026-08-20T00:00:00Z"
        quoted = (
            'const r = await tools.exec_command({"cmd":"python3 '
            '/x/run_subagent.py --agent explorer --cwd /repo --prompt task"});'
        )
        listing = "python3 /x/run_subagent.py --list"
        prose = (
            "The runner lives at /x/run_subagent.py, but this sentence does not "
            "invoke python or provide runner flags."
        )

        parsed = MODULE._parse_invocation(timestamp, quoted)

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.agent, "explorer")
        self.assertEqual(parsed.cwd, "/repo")
        self.assertEqual(parsed.prompt_chars, 4)
        self.assertIsNone(MODULE._parse_invocation(timestamp, listing))
        self.assertIsNone(MODULE._parse_invocation(timestamp, prose))

    def test_dynamic_runner_command_accepts_direct_and_derived_cmd_forms(self) -> None:
        direct = (
            'const args=["python3","/x/run_subagent.py","--agent","explorer"];'
            'const r=await tools.exec_command({cmd:args.map(q).join(" ")});'
        )
        derived = (
            'const args=["python3","/x/run_subagent.py","--agent","explorer"];'
            'const cmd=args.map(q).join(" ");'
            'const r=await tools.exec_command({cmd,yield_time_ms:30000});'
        )

        self.assertTrue(MODULE._contains_dynamic_runner_command(direct))
        self.assertTrue(MODULE._contains_dynamic_runner_command(derived))

    def test_dynamic_runner_shape_must_be_the_actual_exec_cmd_property(self) -> None:
        side_object = (
            'const args=["python3","/x/run_subagent.py","--agent","explorer"];'
            'const audit={cmd:args.map(q).join(" ")};'
            'const r=await tools.exec_command({cmd:"some_other_program"});'
        )
        non_cmd_reference = (
            'const args=["python3","/x/run_subagent.py","--agent","explorer"];'
            'const cmd=args.map(q).join(" ");'
            'const r=await tools.exec_command({note:cmd,cmd:"some_other_program"});'
        )
        commented_call = (
            'const args=["python3","/x/run_subagent.py","--agent","explorer"];\n'
            '// tools.exec_command({cmd:args.map(q).join(" ")});\n'
            'const r=await tools.exec_command({cmd:"some_other_program"});'
        )
        lookalike_receiver = (
            'const args=["python3","/x/run_subagent.py","--agent","explorer"];'
            'const r=await fake_tools.exec_command({cmd:args.map(q).join(" ")});'
        )
        nested_receiver = (
            'const args=["python3","/x/run_subagent.py","--agent","explorer"];'
            'const r=await obj.tools.exec_command({cmd:args.map(q).join(" ")});'
        )

        self.assertFalse(MODULE._contains_dynamic_runner_command(side_object))
        self.assertFalse(MODULE._contains_dynamic_runner_command(non_cmd_reference))
        self.assertFalse(MODULE._contains_dynamic_runner_command(commented_call))
        self.assertFalse(MODULE._contains_dynamic_runner_command(lookalike_receiver))
        self.assertFalse(MODULE._contains_dynamic_runner_command(nested_receiver))

    def test_selected_direct_poll_output_recovers_terminal_with_lowercase_session_marker(self) -> None:
        session_id = "01a01979-f2da-7c00-80b2-65ee2aea9ade"
        terminal = {
            "cli": "minimax",
            "status": "success",
            "exit_code": 0,
            "transport_exit_code": 0,
            "cli_exit_code": 0,
            "termination_reason": "cli_exit",
            "agent_status": "DONE",
        }
        activity = (
            "[sub-agent] activity cli=minimax elapsed=1s event=result "
            "session=external-1"
        )
        records = [
            {
                "timestamp": "t0",
                "type": "session_meta",
                "payload": {"id": session_id, "cwd": "/repo"},
            },
            {
                "timestamp": "t1",
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "call_id": "runner",
                    "name": "exec",
                    "input": (
                        'const r=await tools.exec_command({"cmd":"python3 '
                        '/x/run_subagent.py --agent explorer --cwd /repo '
                        '--dialogue --prompt task"});'
                    ),
                },
            },
            {
                "timestamp": "t2",
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": "runner",
                    "output": [
                        {"type": "input_text", "text": "tool display metadata"},
                        {"type": "input_text", "text": activity},
                        {"type": "input_text", "text": "session_id=42"},
                    ],
                },
            },
            {
                "timestamp": "t3",
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "call_id": "poll",
                    "name": "exec",
                    "input": (
                        "const r=await tools.write_stdin({session_id:42,"
                        'chars:""});'
                    ),
                },
            },
            {
                "timestamp": "t4",
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": "poll",
                    "output": [
                        {"type": "input_text", "text": "poll metadata"},
                        {
                            "type": "input_text",
                            "text": activity + "\n" + json.dumps(terminal),
                        },
                    ],
                },
            },
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            rollout = Path(temp_dir) / "rollout.jsonl"
            rollout.write_text(
                "".join(json.dumps(item) + "\n" for item in records),
                encoding="utf-8",
            )
            capture = MODULE.capture_session(session_id, rollout)

        self.assertEqual([item.agent for item in capture.invocations], ["explorer"])
        self.assertEqual(len(capture.terminals), 1)
        self.assertEqual(capture.terminals[0].agent_status, "DONE")
        self.assertEqual(
            [(item.elapsed_seconds, item.event) for item in capture.activity_timeline],
            [(1, "result"), (1, "result")],
        )

    def test_cell_wait_chain_recovers_selected_activity_and_terminal(self) -> None:
        session_id = "01a01f31-6655-7972-9df8-605ccb483b25"
        external_session = "0d0da7da-d575-41ba-9989-07a1f622fe89"
        truncated_session = "0d0da7da-d575-41ba-9989-07a1f"
        unrelated_session = "11111111-2222-4333-8444-555555555555"
        terminal = {
            "cli": "minimax",
            "status": "success",
            "exit_code": 0,
            "transport_exit_code": 0,
            "cli_exit_code": 0,
            "termination_reason": "cli_exit",
            "agent_status": "DONE",
        }

        def activity(elapsed: int, event: str, session: str) -> str:
            return (
                "[sub-agent] activity cli=minimax "
                f"elapsed={elapsed}s event={event} session={session}"
            )

        records = [
            {"type": "session_meta", "payload": {"id": session_id, "cwd": "/repo"}},
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "call_id": "runner",
                    "name": "exec",
                    "input": (
                        'const r=await tools.exec_command({"cmd":"python3 '
                        '/x/run_subagent.py --agent explorer --cwd /repo '
                        '--prompt task"});'
                    ),
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": "runner",
                    "output": (
                        "Script running with cell ID 133\n"
                        "Wall time 10.0 seconds\nOutput:\n"
                    ),
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "call_id": "wait-runner",
                    "name": "wait",
                    "arguments": json.dumps({"cell_id": "133"}),
                },
            },
            {
                "timestamp": "t1",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "wait-runner",
                    "output": [
                        {
                            "type": "input_text",
                            "text": activity(1, "thinking", truncated_session),
                        }
                    ],
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "call_id": "poll",
                    "name": "exec",
                    "input": (
                        "const r=await tools.write_stdin({session_id:77,"
                        'chars:""});'
                    ),
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": "poll",
                    "output": (
                        "Script running with cell ID 134\n"
                        "Wall time 10.0 seconds\nOutput:\n"
                    ),
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "call_id": "wait-poll",
                    "name": "wait",
                    "arguments": json.dumps({"cell_id": 134}),
                },
            },
            {
                "timestamp": "t2",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "wait-poll",
                    "output": [
                        {
                            "type": "input_text",
                            "text": (
                                activity(2, "result", external_session)
                                + "\n"
                                + json.dumps(terminal)
                            ),
                        }
                    ],
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "call_id": "unrelated-poll",
                    "name": "exec",
                    "input": (
                        "const r=await tools.write_stdin({session_id:88,"
                        'chars:""});'
                    ),
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": "unrelated-poll",
                    "output": (
                        "Script running with cell ID 135\n"
                        "Wall time 10.0 seconds\nOutput:\n"
                    ),
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "call_id": "wait-unrelated",
                    "name": "wait",
                    "arguments": json.dumps({"cell_id": 135}),
                },
            },
            {
                "timestamp": "t3",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "wait-unrelated",
                    "output": [
                        {
                            "type": "input_text",
                            "text": (
                                activity(3, "result", unrelated_session)
                                + "\n"
                                + json.dumps(terminal)
                            ),
                        }
                    ],
                },
            },
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            rollout = Path(temp_dir) / "rollout.jsonl"
            rollout.write_text(
                "".join(json.dumps(item) + "\n" for item in records),
                encoding="utf-8",
            )
            capture = MODULE.capture_session(session_id, rollout)

        self.assertEqual([item.agent for item in capture.invocations], ["explorer"])
        self.assertEqual(
            [(item.external_session, item.event) for item in capture.activity_timeline],
            [(external_session, "thinking"), (external_session, "result")],
        )
        self.assertEqual(len(capture.terminals), 1)
        self.assertEqual(capture.terminals[0].agent_status, "DONE")
        self.assertEqual(capture.canonicalized_session_prefixes, 1)

    def test_nested_cell_marker_cannot_attach_unrelated_wait_terminal(self) -> None:
        session_id = "01a01f31-6655-7972-9df8-605ccb483b25"
        external_session = "11111111-2222-4333-8444-555555555555"
        terminal = {
            "cli": "minimax",
            "status": "success",
            "exit_code": 0,
            "transport_exit_code": 0,
            "cli_exit_code": 0,
            "termination_reason": "cli_exit",
            "agent_status": "DONE",
        }
        records = [
            {"type": "session_meta", "payload": {"id": session_id, "cwd": "/repo"}},
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "call_id": "runner",
                    "name": "exec",
                    "input": (
                        'const r=await tools.exec_command({"cmd":"python3 '
                        '/x/run_subagent.py --agent explorer --cwd /repo '
                        '--prompt task"});'
                    ),
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": "runner",
                    "output": {
                        "output": "Script running with cell ID 133",
                        "exit_code": 0,
                        "wall_time_seconds": 1.0,
                    },
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "call_id": "unrelated-wait",
                    "name": "wait",
                    "arguments": json.dumps({"cell_id": 133}),
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "unrelated-wait",
                    "output": (
                        "[sub-agent] activity cli=minimax elapsed=1s event=result "
                        f"session={external_session}\n{json.dumps(terminal)}"
                    ),
                },
            },
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            rollout = Path(temp_dir) / "rollout.jsonl"
            rollout.write_text(
                "".join(json.dumps(item) + "\n" for item in records),
                encoding="utf-8",
            )
            capture = MODULE.capture_session(session_id, rollout)

        self.assertEqual(capture.activity_timeline, [])
        self.assertEqual(capture.terminals, [])

    def test_cell_wait_requires_unique_forward_ordered_chain(self) -> None:
        session_id = "01a01f31-6655-7972-9df8-605ccb483b25"
        terminal = json.dumps(
            {
                "cli": "minimax",
                "status": "success",
                "exit_code": 0,
                "transport_exit_code": 0,
                "cli_exit_code": 0,
                "termination_reason": "cli_exit",
                "agent_status": "DONE",
            }
        )
        common = [
            {"type": "session_meta", "payload": {"id": session_id, "cwd": "/repo"}},
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "call_id": "runner",
                    "name": "exec",
                    "input": (
                        'const r=await tools.exec_command({"cmd":"python3 '
                        '/x/run_subagent.py --agent explorer --cwd /repo '
                        '--prompt task"});'
                    ),
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": "runner",
                    "output": "Script running with cell ID 133",
                },
            },
        ]

        def wait(call_id: str) -> dict[str, object]:
            return {
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "call_id": call_id,
                    "name": "wait",
                    "arguments": json.dumps({"cell_id": 133}),
                },
            }

        def output(call_id: str) -> dict[str, object]:
            return {
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": terminal,
                },
            }

        invalid_tails = (
            [wait("wait-one"), output("wait-one"), wait("wait-two"), output("wait-two")],
            [output("wait-one"), wait("wait-one")],
        )
        for tail in invalid_tails:
            with self.subTest(tail=tail):
                with tempfile.TemporaryDirectory() as temp_dir:
                    rollout = Path(temp_dir) / "rollout.jsonl"
                    rollout.write_text(
                        "".join(json.dumps(item) + "\n" for item in common + tail),
                        encoding="utf-8",
                    )
                    capture = MODULE.capture_session(session_id, rollout)
                self.assertEqual(capture.activity_timeline, [])
                self.assertEqual(capture.terminals, [])

    def test_unique_truncated_uuid_prefix_is_canonicalized(self) -> None:
        session_id = "01a01e34-039b-79d1-9910-ff773e5b6526"
        full = "a144a3fa-0e2f-4d7e-8d56-aaaccb8fd9ef"
        truncated = "a144a3fa-0e2f-4d7e-8d56-a"
        records = [
            {"type": "session_meta", "payload": {"id": session_id, "cwd": "/repo"}},
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "call_id": "runner",
                    "name": "exec",
                    "input": (
                        'const r=await tools.exec_command({"cmd":"python3 '
                        '/x/run_subagent.py --agent explorer --cwd /repo '
                        '--prompt task"});'
                    ),
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": "runner",
                    "output": [
                        {
                            "type": "input_text",
                            "text": (
                                "[sub-agent] activity cli=minimax elapsed=62s "
                                f"event=tool_result session={full}\n"
                                "[sub-agent] activity cli=minimax elapsed=64s "
                                f"event=thinking session={truncated}"
                            ),
                        }
                    ],
                },
            },
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            rollout = Path(temp_dir) / "rollout.jsonl"
            rollout.write_text(
                "".join(json.dumps(item) + "\n" for item in records),
                encoding="utf-8",
            )
            capture = MODULE.capture_session(session_id, rollout)

        self.assertEqual(set(capture.activities), {full})
        self.assertEqual(
            [item.external_session for item in capture.activity_timeline],
            [full, full],
        )
        self.assertEqual(capture.canonicalized_session_prefixes, 1)
        self.assertIn(
            "external_session_prefix_canonicalized",
            {signal.name for signal in MODULE._diagnostic_signals(capture)},
        )

    def test_ambiguous_truncated_uuid_prefix_remains_separate(self) -> None:
        prefix = "12345678-1234-4234-8234-"
        full_one = prefix + "aaaaaaaaaaaa"
        full_two = prefix + "bbbbbbbbbbbb"
        capture = MODULE.Capture(
            session_id="01a01e34-039b-79d1-9910-ff773e5b6526",
            source_path=Path("/tmp/sanitized-rollout.jsonl"),
            activity_timeline=[
                MODULE.Activity(prefix, 1, "thinking"),
                MODULE.Activity(full_one, 2, "result"),
                MODULE.Activity(full_two, 3, "result"),
            ],
        )
        for item in capture.activity_timeline:
            capture.activities[item.external_session][item.event] += 1
            capture.max_elapsed[item.external_session] = item.elapsed_seconds

        MODULE._canonicalize_activity_sessions(capture)

        self.assertEqual(capture.canonicalized_session_prefixes, 0)
        self.assertEqual(
            [item.external_session for item in capture.activity_timeline],
            [prefix, full_one, full_two],
        )
        self.assertFalse(MODULE.session_sets_intersect({prefix}, {full_one, full_two}))

    def test_ambiguous_prefix_across_separate_polls_is_order_independent(self) -> None:
        session_id = "01a01e34-039b-79d1-9910-ff773e5b6526"
        prefix = "12345678-1234-4234-8234-"
        full_one = prefix + "aaaaaaaaaaaa"
        full_two = prefix + "bbbbbbbbbbbb"
        terminal = json.dumps(
            {
                "cli": "minimax",
                "status": "success",
                "exit_code": 0,
                "transport_exit_code": 0,
                "cli_exit_code": 0,
                "termination_reason": "cli_exit",
                "agent_status": "DONE",
            }
        )

        def envelope(cell_id: int) -> str:
            return (
                f"Script running with cell ID {cell_id}\n"
                "Wall time 10.0 seconds\nOutput:\n"
            )

        def activity(session: str) -> str:
            return (
                "[sub-agent] activity cli=minimax elapsed=1s "
                f"event=result session={session}"
            )

        base = [
            {"type": "session_meta", "payload": {"id": session_id, "cwd": "/repo"}},
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "call_id": "runner",
                    "name": "exec",
                    "input": (
                        'const r=await tools.exec_command({"cmd":"python3 '
                        '/x/run_subagent.py --agent explorer --cwd /repo '
                        '--prompt task"});'
                    ),
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": "runner",
                    "output": envelope(100),
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "call_id": "wait-runner",
                    "name": "wait",
                    "arguments": json.dumps({"cell_id": 100}),
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "wait-runner",
                    "output": activity(prefix),
                },
            },
        ]

        def poll(name: str, cell_id: int, process_id: int, session: str) -> list[dict[str, object]]:
            return [
                {
                    "type": "response_item",
                    "payload": {
                        "type": "custom_tool_call",
                        "call_id": f"poll-{name}",
                        "name": "exec",
                        "input": (
                            "const r=await tools.write_stdin({"
                            f"session_id:{process_id},chars:\"\"}});"
                        ),
                    },
                },
                {
                    "type": "response_item",
                    "payload": {
                        "type": "custom_tool_call_output",
                        "call_id": f"poll-{name}",
                        "output": envelope(cell_id),
                    },
                },
                {
                    "type": "response_item",
                    "payload": {
                        "type": "function_call",
                        "call_id": f"wait-{name}",
                        "name": "wait",
                        "arguments": json.dumps({"cell_id": cell_id}),
                    },
                },
                {
                    "type": "response_item",
                    "payload": {
                        "type": "function_call_output",
                        "call_id": f"wait-{name}",
                        "output": activity(session) + "\n" + terminal,
                    },
                },
            ]

        poll_blocks = (
            poll("one", 101, 201, full_one),
            poll("two", 102, 202, full_two),
        )
        for ordered_blocks in (poll_blocks, tuple(reversed(poll_blocks))):
            with self.subTest(order=[block[0]["payload"] for block in ordered_blocks]):
                records = base + [item for block in ordered_blocks for item in block]
                with tempfile.TemporaryDirectory() as temp_dir:
                    rollout = Path(temp_dir) / "rollout.jsonl"
                    rollout.write_text(
                        "".join(json.dumps(item) + "\n" for item in records),
                        encoding="utf-8",
                    )
                    capture = MODULE.capture_session(session_id, rollout)

                self.assertEqual(capture.terminals, [])
                self.assertEqual(
                    [item.external_session for item in capture.activity_timeline],
                    [prefix],
                )

    def test_direct_poll_prefix_can_attach_later_cell_poll_full_uuid(self) -> None:
        session_id = "01a01f31-6655-7972-9df8-605ccb483b25"
        full = "a144a3fa-0e2f-4d7e-8d56-aaaccb8fd9ef"
        truncated = "a144a3fa-0e2f-4d7e-8d56-a"
        terminal = {
            "cli": "minimax",
            "status": "success",
            "exit_code": 0,
            "transport_exit_code": 0,
            "cli_exit_code": 0,
            "termination_reason": "cli_exit",
            "agent_status": "DONE",
        }

        def activity(session: str) -> str:
            return (
                "[sub-agent] activity cli=minimax elapsed=1s "
                f"event=result session={session}"
            )

        records = [
            {"type": "session_meta", "payload": {"id": session_id, "cwd": "/repo"}},
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "call_id": "runner",
                    "name": "exec",
                    "input": (
                        'const r=await tools.exec_command({"cmd":"python3 '
                        '/x/run_subagent.py --agent explorer --cwd /repo '
                        '--prompt task"});'
                    ),
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": "runner",
                    "output": {
                        "session_id": 77,
                        "output": "started",
                        "wall_time_seconds": 1.0,
                    },
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "call_id": "direct-poll",
                    "name": "exec",
                    "input": 'const r=await tools.write_stdin({session_id:77,chars:""});',
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": "direct-poll",
                    "output": activity(truncated),
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "call_id": "cell-poll",
                    "name": "exec",
                    "input": 'const r=await tools.write_stdin({session_id:88,chars:""});',
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": "cell-poll",
                    "output": (
                        "Script running with cell ID 133\n"
                        "Wall time 10.0 seconds\nOutput:\n"
                    ),
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "call_id": "wait-cell-poll",
                    "name": "wait",
                    "arguments": json.dumps({"cell_id": 133}),
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "wait-cell-poll",
                    "output": activity(full) + "\n" + json.dumps(terminal),
                },
            },
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            rollout = Path(temp_dir) / "rollout.jsonl"
            rollout.write_text(
                "".join(json.dumps(item) + "\n" for item in records),
                encoding="utf-8",
            )
            capture = MODULE.capture_session(session_id, rollout)

        self.assertEqual(
            [item.external_session for item in capture.activity_timeline],
            [full, full],
        )
        self.assertEqual(len(capture.terminals), 1)
        self.assertEqual(capture.canonicalized_session_prefixes, 1)

    def test_dynamic_runner_command_uses_strict_framing_without_inventing_invocation_shape(self) -> None:
        session_id = "01a01979-f2da-7c00-80b2-65ee2aea9ade"
        terminal = {
            "cli": "minimax",
            "status": "success",
            "exit_code": 0,
            "transport_exit_code": 0,
            "cli_exit_code": 0,
            "termination_reason": "cli_exit",
            "agent_status": "DONE",
        }
        activity = (
            "[sub-agent] activity cli=minimax elapsed=3s event=result "
            "session=external-2"
        )
        dynamic_input = (
            'const args=["python3","/x/run_subagent.py","--agent",'
            '"explorer","--cwd","/repo","--prompt",prompt];'
            'const r=await tools.exec_command({cmd:args.map(q).join(" ")});'
        )
        records = [
            {
                "timestamp": "t0",
                "type": "session_meta",
                "payload": {"id": session_id, "cwd": "/repo"},
            },
            {
                "timestamp": "t1",
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "call_id": "runner",
                    "name": "exec",
                    "input": dynamic_input,
                },
            },
            {
                "timestamp": "t2",
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": "runner",
                    "output": [
                        {
                            "type": "input_text",
                            "text": json.dumps(
                                {
                                    "session_id": 77,
                                    "exit_code": None,
                                    "wall_time_seconds": 0.5,
                                    "output": activity,
                                }
                            ),
                        },
                    ],
                },
            },
            {
                "timestamp": "t3",
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "call_id": "poll",
                    "name": "exec",
                    "input": "const r=await tools.write_stdin({session_id:77});",
                },
            },
            {
                "timestamp": "t4",
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": "poll",
                    "output": [
                        {
                            "type": "input_text",
                            "text": activity + "\n" + json.dumps(terminal),
                        }
                    ],
                },
            },
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            rollout = Path(temp_dir) / "rollout.jsonl"
            rollout.write_text(
                "".join(json.dumps(item) + "\n" for item in records),
                encoding="utf-8",
            )
            capture = MODULE.capture_session(session_id, rollout)
            report = MODULE.render_markdown(capture, "now")

        self.assertEqual(capture.invocations, [])
        self.assertEqual(capture.unparsed_runner_calls, 1)
        self.assertEqual(len(capture.terminals), 1)
        self.assertIn("dynamic command shape", report)
        self.assertNotIn("| unknown | definition/default |", report)

    def test_runner_name_in_side_string_cannot_select_another_command(self) -> None:
        session_id = "01a01979-f2da-7c00-80b2-65ee2aea9ade"
        terminal = {
            "cli": "minimax",
            "status": "success",
            "exit_code": 0,
            "transport_exit_code": 0,
            "cli_exit_code": 0,
            "termination_reason": "cli_exit",
            "agent_status": "DONE",
        }
        records = [
            {"type": "session_meta", "payload": {"id": session_id, "cwd": "/repo"}},
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "call_id": "other-command",
                    "name": "exec",
                    "input": (
                        'const note="/x/run_subagent.py";'
                        'const args=["some_other_program"];'
                        'const r=await tools.exec_command({cmd:args.map(q).join(" ")});'
                    ),
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": "other-command",
                    "output": [
                        {
                            "type": "input_text",
                            "text": json.dumps(
                                {
                                    "session_id": 88,
                                    "exit_code": None,
                                    "wall_time_seconds": 0.5,
                                    "output": (
                                        "[sub-agent] activity cli=minimax elapsed=1s "
                                        "event=result session=external-fake"
                                    ),
                                }
                            ),
                        }
                    ],
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "call_id": "poll",
                    "name": "exec",
                    "input": "const r=await tools.write_stdin({session_id:88});",
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": "poll",
                    "output": [
                        {
                            "type": "input_text",
                            "text": json.dumps(terminal),
                        }
                    ],
                },
            },
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            rollout = Path(temp_dir) / "rollout.jsonl"
            rollout.write_text(
                "".join(json.dumps(item) + "\n" for item in records),
                encoding="utf-8",
            )
            capture = MODULE.capture_session(session_id, rollout)

        self.assertEqual(capture.unparsed_runner_calls, 0)
        self.assertEqual(capture.activity_timeline, [])
        self.assertEqual(capture.terminals, [])

    def test_report_surfaces_activity_and_evidence_optimization_signals(self) -> None:
        capture = MODULE.Capture(
            session_id="session-12345678",
            source_path=Path("rollout.jsonl"),
            invocations=[MODULE.Invocation("t0", agent="explorer", dialogue=True)],
            terminals=[
                MODULE.Terminal(
                    "t1",
                    "success",
                    "0",
                    "0",
                    "cli_exit",
                    "DONE_WITH_CONCERNS",
                    0,
                    2,
                    "none",
                    "none",
                )
            ],
        )
        elapsed = 0
        events = ["tool:Bash", "tool_result:error"]
        events.extend(["tool:Read"] * 17)
        events.extend(["tool:Grep"] * 3)
        for event in events:
            capture.activity_timeline.append(
                MODULE.Activity("external-1", elapsed, event)
            )
            capture.activities["external-1"][event] += 1
            elapsed += 1
        capture.activity_timeline.append(
            MODULE.Activity("external-1", elapsed + 103, "result")
        )
        capture.activities["external-1"]["result"] += 1

        report = MODULE.render_markdown(capture, "now")

        self.assertIn("## Diagnostic Signals", report)
        self.assertIn("tool_error_event", report)
        self.assertIn("explorer_tool_mismatch", report)
        self.assertIn("long_activity_gap", report)
        self.assertIn("104", report)
        self.assertIn("zero_terminal_evidence", report)
        self.assertIn("read_heavy_exploration", report)
        self.assertNotIn("No known runner failure signature", report)

    def test_dynamic_runner_without_terminal_gets_attachment_lead(self) -> None:
        capture = MODULE.Capture(
            session_id="session-12345678",
            source_path=Path("rollout.jsonl"),
            unparsed_runner_calls=1,
        )

        leads = MODULE._optimization_leads(capture)

        self.assertIn(
            "No MiniMax terminal record was captured; inspect process attachment "
            "and output routing.",
            leads,
        )

    def test_signal_thresholds_do_not_overstate_small_or_short_activity(self) -> None:
        activities = [("external-1", index, "tool:Read") for index in range(14)]
        activities.extend(
            [
                ("external-1", 14, "tool:Grep"),
                ("external-1", 73, "result"),
            ]
        )

        signals = MODULE.analyze_signals(
            (("explorer", False),),
            tuple(activities),
            (("DONE", 1, 0),),
        )

        self.assertEqual(signals, ())

    def test_zero_evidence_signal_requires_dialogue_invocation(self) -> None:
        signals = MODULE.analyze_signals(
            (("explorer", False),),
            (),
            (("DONE_WITH_CONCERNS", 0, 1),),
        )

        self.assertNotIn(
            "zero_terminal_evidence", {signal.name for signal in signals}
        )

    def test_zero_evidence_signal_does_not_guess_across_mixed_invocations(self) -> None:
        signals = MODULE.analyze_signals(
            (("explorer", True), ("writer", False)),
            (),
            (("DONE_WITH_CONCERNS", 0, 1),),
        )

        self.assertNotIn(
            "zero_terminal_evidence", {signal.name for signal in signals}
        )

    def test_capture_omits_raw_prompt_command_and_secret(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            session_id = "01a01979-f2da-7c00-80b2-65ee2aea9ade"
            rollout = root / f"rollout-{session_id}.jsonl"
            _write_rollout(rollout, session_id)

            capture = MODULE.capture_session(session_id, rollout)
            report = MODULE.render_markdown(capture, "2026-08-19T00:03:00Z")

        self.assertEqual(len(capture.invocations), 1)
        self.assertEqual(capture.terminals[0].resolved_model, "MiniMax-M3")
        self.assertEqual(capture.terminals[0].resolved_effort, "high")
        self.assertEqual(
            capture.terminals[0].resolved_tools,
            ("Read", "Glob", "Grep", "StructuredOutput"),
        )
        self.assertEqual(capture.terminals[0].resolved_tools_mode, "explicit")
        self.assertEqual(
            capture.terminals[0].concern_categories,
            ("permission_or_tooling",),
        )
        self.assertIn("MiniMax-M3", report)
        self.assertIn("permission_or_tooling", report)
        self.assertEqual(capture.invocations[0].agent, "explorer")
        self.assertEqual(capture.invocations[0].allow_command_count, 1)
        self.assertEqual(capture.invocations[0].command_families, ("pytest",))
        self.assertEqual(capture.invocations[0].evidence_path_count, 1)
        self.assertEqual(
            [(item.elapsed_seconds, item.event) for item in capture.activity_timeline],
            [(4, "tool:Read")],
        )
        self.assertEqual(len(capture.terminals), 1)
        self.assertEqual(capture.terminals[0].agent_status, "BLOCKED")
        self.assertNotIn("secret task text", report)
        self.assertNotIn("pytest -q", report)
        self.assertNotIn("hunter2", report)
        self.assertNotIn("curl", report)
        self.assertNotIn("ghp_abcdefghijklmnop", report)
        self.assertIn("evidence_incomplete", report)
        self.assertIn("missing_required_evidence", report)

    def test_terminal_rejects_arbitrary_model_and_distinguishes_unknown_tools(self) -> None:
        terminal = MODULE._terminal_from_dict(
            "t0",
            {
                "cli": "minimax",
                "status": "success",
                "exit_code": 0,
                "transport_exit_code": 0,
                "cli_exit_code": 0,
                "termination_reason": "cli_exit",
                "agent_status": "DONE",
                "runner_context": {
                    "model": "arbitrary historical prose PRIVATE_VALUE=hunter2",
                    "effort": "high",
                    "permission": "read-only",
                },
            },
        )

        self.assertIsNotNone(terminal)
        assert terminal is not None
        self.assertEqual(terminal.resolved_model, "other")
        self.assertEqual(terminal.resolved_tools_mode, "unknown")
        report = MODULE.render_markdown(
            MODULE.Capture("session-12345678", Path("rollout.jsonl"), terminals=[terminal]),
            "now",
        )
        self.assertIn("unknown", report)
        self.assertNotIn("arbitrary historical prose", report)
        self.assertNotIn("hunter2", report)

        default_terminal = MODULE._terminal_from_dict(
            "t1",
            {
                "cli": "minimax",
                "status": "success",
                "exit_code": 0,
                "transport_exit_code": 0,
                "cli_exit_code": 0,
                "termination_reason": "cli_exit",
                "runner_context": {
                    "model": "MiniMax-M3",
                    "effort": "high",
                    "permission": "yolo",
                    "tools_mode": "default",
                    "tools": [],
                },
            },
        )
        self.assertIsNotNone(default_terminal)
        assert default_terminal is not None
        default_report = MODULE.render_markdown(
            MODULE.Capture(
                "session-12345678",
                Path("rollout.jsonl"),
                terminals=[default_terminal],
            ),
            "now",
        )
        self.assertIn("| yolo | default |", default_report)

    def test_terminal_is_recovered_from_nested_exec_output_json(self) -> None:
        terminal = {
            "cli": "minimax",
            "status": "success",
            "exit_code": 0,
            "transport_exit_code": 0,
            "cli_exit_code": 0,
            "termination_reason": "cli_exit",
            "agent_status": "DONE",
        }
        wrapper = "Warning: truncated output metadata\nTotal output lines: 8\n" + json.dumps(
            {
                "output": (
                    "[sub-agent] activity cli=minimax elapsed=1s event=result "
                    "session=external-1\n" + json.dumps(terminal)
                ),
                "exit_code": 0,
                "wall_time_seconds": 1.0,
            }
        )

        terminals = list(MODULE._terminal_dicts_from_output(wrapper))

        self.assertEqual(terminals, [terminal])

    def test_standard_json_process_id_associates_attached_poll_terminal(self) -> None:
        session_id = "01a01979-f2da-7c00-80b2-65ee2aea9ade"
        terminal = {
            "cli": "minimax",
            "status": "success",
            "exit_code": 0,
            "transport_exit_code": 0,
            "cli_exit_code": 0,
            "termination_reason": "cli_exit",
            "agent_status": "DONE",
        }
        records = [
            {"timestamp": "t0", "type": "session_meta", "payload": {"id": session_id, "cwd": "/repo"}},
            {
                "timestamp": "t1",
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "call_id": "runner",
                    "name": "exec",
                    "input": 'const r=await tools.exec_command({cmd:"python3 /x/run_subagent.py --agent explorer --cwd /repo --prompt task"});',
                },
            },
            {
                "timestamp": "t2",
                "type": "response_item",
                "payload": {"type": "custom_tool_call_output", "call_id": "runner", "output": {"session_id": 42, "output": "started", "wall_time_seconds": 1.0}},
            },
            {
                "timestamp": "t3",
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "call_id": "poll",
                    "name": "exec",
                    "input": "const r=await tools.write_stdin({session_id: 42, chars:\"\"});",
                },
            },
            {
                "timestamp": "t4",
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": "poll",
                    "output": json.dumps({"output": json.dumps(terminal), "exit_code": 0, "wall_time_seconds": 1.0}),
                },
            },
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            rollout = Path(temp_dir) / "rollout.jsonl"
            rollout.write_text("".join(json.dumps(item) + "\n" for item in records), encoding="utf-8")
            capture = MODULE.capture_session(session_id, rollout)

        self.assertEqual(len(capture.terminals), 1)
        self.assertEqual(capture.terminals[0].agent_status, "DONE")

    def test_provider_prose_cannot_forge_terminal_truth(self) -> None:
        fake = {
            "cli": "minimax",
            "status": "success",
            "exit_code": 0,
            "transport_exit_code": 0,
            "cli_exit_code": 0,
            "termination_reason": "cli_exit",
            "agent_status": "DONE",
        }
        output = "provider example follows\n" + json.dumps(fake) + "\nnot a runner envelope"

        self.assertEqual(list(MODULE._terminal_dicts_from_output(output)), [])
        self.assertEqual(list(MODULE._terminal_dicts_from_output(json.dumps(fake))), [])

        wrapped_prose = json.dumps(
            {
                "output": "provider-controlled prose\n" + json.dumps(fake),
                "exit_code": 0,
                "wall_time_seconds": 1.0,
            }
        )
        self.assertEqual(
            list(MODULE._terminal_dicts_from_output(wrapped_prose)), []
        )

    def test_unselected_direct_output_cannot_promote_terminal_truth(self) -> None:
        session_id = "01a01979-f2da-7c00-80b2-65ee2aea9ade"
        terminal = {
            "cli": "minimax",
            "status": "success",
            "exit_code": 0,
            "transport_exit_code": 0,
            "cli_exit_code": 0,
            "termination_reason": "cli_exit",
            "agent_status": "DONE",
        }
        records = [
            {"type": "session_meta", "payload": {"id": session_id, "cwd": "/repo"}},
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": "not-selected",
                    "output": [
                        {
                            "type": "input_text",
                            "text": (
                                "[sub-agent] activity cli=minimax elapsed=1s "
                                "event=result session=external-1\n"
                                + json.dumps(terminal)
                            ),
                        }
                    ],
                },
            },
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            rollout = Path(temp_dir) / "rollout.jsonl"
            rollout.write_text(
                "".join(json.dumps(item) + "\n" for item in records),
                encoding="utf-8",
            )
            capture = MODULE.capture_session(session_id, rollout)

        self.assertEqual(capture.terminals, [])

    def test_provider_prose_session_id_cannot_attach_unrelated_poll(self) -> None:
        session_id = "01a01979-f2da-7c00-80b2-65ee2aea9ade"
        terminal = {
            "cli": "minimax",
            "status": "success",
            "exit_code": 0,
            "transport_exit_code": 0,
            "cli_exit_code": 0,
            "termination_reason": "cli_exit",
            "agent_status": "DONE",
        }
        records = [
            {"type": "session_meta", "payload": {"id": session_id, "cwd": "/repo"}},
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "call_id": "runner",
                    "name": "exec",
                    "input": 'const r=await tools.exec_command({cmd:"python3 /x/run_subagent.py --agent explorer --cwd /repo --prompt task"});',
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": "runner",
                    "output": {
                        "wall_time_seconds": 1.0,
                        "exit_code": 0,
                        "output": "provider prose says session_id: 42",
                    },
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "call_id": "poll",
                    "name": "exec",
                    "input": "const r=await tools.write_stdin({session_id: 42, chars:\"\"});",
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": "poll",
                    "output": {
                        "wall_time_seconds": 1.0,
                        "exit_code": 0,
                        "output": json.dumps(terminal),
                    },
                },
            },
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            rollout = Path(temp_dir) / "rollout.jsonl"
            rollout.write_text(
                "".join(json.dumps(item) + "\n" for item in records),
                encoding="utf-8",
            )
            capture = MODULE.capture_session(session_id, rollout)

        self.assertEqual(capture.terminals, [])

    def test_terminal_identity_keeps_distinct_exit_truth(self) -> None:
        first = MODULE.Terminal("t", "error", "1", "0", "cli_exit", "BLOCKED", 0, 0, "x", "protocol")
        second = MODULE.Terminal("t", "error", "1", "2", "cli_exit", "BLOCKED", 0, 0, "x", "protocol")

        self.assertNotEqual(MODULE._terminal_key(first), MODULE._terminal_key(second))

    def test_unknown_terminal_strings_are_persisted_only_as_categories(self) -> None:
        terminal = {
            "cli": "minimax",
            "status": "error",
            "exit_code": 1,
            "transport_exit_code": 1,
            "cli_exit_code": 1,
            "termination_reason": "curl secret-command",
            "agent_status": "rm secret-agent",
            "blocker": {"kind": "cat secret-path"},
            "error": "unknown raw error",
        }
        parsed = MODULE._terminal_from_dict("t", terminal)
        assert parsed is not None
        capture = MODULE.Capture("session", Path("rollout"), terminals=[parsed])
        report = MODULE.render_markdown(capture, "now")

        self.assertEqual(parsed.termination_reason, "other")
        self.assertEqual(parsed.agent_status, "other")
        self.assertEqual(parsed.blocker_kind, "other")
        self.assertNotIn("secret-command", report)
        self.assertNotIn("secret-agent", report)
        self.assertNotIn("secret-path", report)

    def test_explicit_output_is_non_overwriting(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            session_id = "01a01979-f2da-7c00-80b2-65ee2aea9ade"
            rollout = root / f"rollout-{session_id}.jsonl"
            output = root / "report.md"
            _write_rollout(rollout, session_id)

            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                first = MODULE.main(
                    [
                        "--session-id",
                        session_id,
                        "--session-file",
                        str(rollout),
                        "--output",
                        str(output),
                    ]
                )
                second = MODULE.main(
                    [
                        "--session-id",
                        session_id,
                        "--session-file",
                        str(rollout),
                        "--output",
                        str(output),
                    ]
                )

        self.assertEqual(first, 0)
        self.assertEqual(second, 1)

    def test_default_capture_reuses_existing_report_when_fingerprint_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            session_id = "01a01979-f2da-7c00-80b2-65ee2aea9ade"
            rollout = root / f"rollout-{session_id}.jsonl"
            reports = root / "reports"
            _write_rollout(rollout, session_id)

            first_stdout = io.StringIO()
            second_stdout = io.StringIO()
            with redirect_stdout(first_stdout), redirect_stderr(io.StringIO()):
                first = MODULE.main(
                    [
                        "--session-id",
                        session_id,
                        "--session-file",
                        str(rollout),
                        "--output-root",
                        str(reports),
                    ]
                )
            with redirect_stdout(second_stdout), redirect_stderr(io.StringIO()):
                second = MODULE.main(
                    [
                        "--session-id",
                        session_id,
                        "--session-file",
                        str(rollout),
                        "--output-root",
                        str(reports),
                    ]
                )

            created = list(reports.glob(f"{session_id}-*.md"))

        self.assertEqual(first, 0)
        self.assertEqual(second, 0)
        self.assertEqual(len(created), 1)
        self.assertEqual(first_stdout.getvalue(), second_stdout.getvalue())
        self.assertRegex(created[0].name, rf"^{session_id}-[0-9a-f]{{16}}\.md$")

    def test_concurrent_identical_default_captures_both_reuse_one_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            session_id = "01a01979-f2da-7c00-80b2-65ee2aea9ade"
            rollout = root / f"rollout-{session_id}.jsonl"
            reports = root / "reports"
            _write_rollout(rollout, session_id)
            args = [
                "--session-id",
                session_id,
                "--session-file",
                str(rollout),
                "--output-root",
                str(reports),
            ]
            barrier = threading.Barrier(2)
            exit_codes: list[int] = []

            def capture() -> None:
                barrier.wait()
                exit_codes.append(MODULE.main(args))

            with mock.patch("builtins.print"):
                threads = [threading.Thread(target=capture) for _ in range(2)]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join()

            created = list(reports.glob(f"{session_id}-*.md"))

        self.assertEqual(sorted(exit_codes), [0, 0])
        self.assertEqual(len(created), 1)

    def test_report_schema_change_does_not_reuse_stale_capture(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            session_id = "01a01979-f2da-7c00-80b2-65ee2aea9ade"
            rollout = root / f"rollout-{session_id}.jsonl"
            reports = root / "reports"
            _write_rollout(rollout, session_id)
            args = [
                "--session-id",
                session_id,
                "--session-file",
                str(rollout),
                "--output-root",
                str(reports),
            ]

            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                first = MODULE.main(args)
            with mock.patch.object(
                MODULE, "REPORT_SCHEMA_VERSION", MODULE.REPORT_SCHEMA_VERSION + 1
            ):
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    second = MODULE.main(args)

            created = list(reports.glob(f"{session_id}-*.md"))

        self.assertEqual(first, 0)
        self.assertEqual(second, 0)
        self.assertEqual(len(created), 2)

    def test_existing_report_finds_fingerprint_after_extended_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            session_id = "01a01979-f2da-7c00-80b2-65ee2aea9ade"
            fingerprint = "0123456789abcdef"
            report = root / f"{session_id}-existing.md"
            report.write_text(
                "# MiniMax Subagent Session Capture\n"
                + f"- Session ID: `{session_id}`\n"
                + f"- Report schema version: `{MODULE.REPORT_SCHEMA_VERSION}`\n"
                + "".join(f"- Extended metadata {index}\n" for index in range(20))
                + f"- Capture fingerprint: `{fingerprint}`\n"
                + f"{MODULE.REPORT_COMPLETE_MARKER}\n",
                encoding="utf-8",
            )
            report.chmod(0o600)

            existing = MODULE._existing_report(root, session_id, fingerprint)

        self.assertEqual(existing, report)

    def test_existing_report_rejects_unsafe_mode_and_incomplete_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            session_id = "01a01979-f2da-7c00-80b2-65ee2aea9ade"
            fingerprint = "0123456789abcdef"
            report = root / f"{session_id}-{fingerprint}.md"
            complete = (
                "# MiniMax Subagent Session Capture\n"
                f"- Session ID: `{session_id}`\n"
                f"- Capture fingerprint: `{fingerprint}`\n"
                f"- Report schema version: `{MODULE.REPORT_SCHEMA_VERSION}`\n"
                f"{MODULE.REPORT_COMPLETE_MARKER}\n"
            )
            report.write_text(complete, encoding="utf-8")
            report.chmod(0o644)

            unsafe = MODULE._existing_report(root, session_id, fingerprint)
            report.chmod(0o600)
            report.write_text(complete.replace(MODULE.REPORT_COMPLETE_MARKER, ""), encoding="utf-8")
            incomplete = MODULE._existing_report(root, session_id, fingerprint)

        self.assertIsNone(unsafe)
        self.assertIsNone(incomplete)

    def test_existing_report_rejects_content_over_actual_byte_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            session_id = "01a01979-f2da-7c00-80b2-65ee2aea9ade"
            fingerprint = "0123456789abcdef"
            report = root / f"{session_id}-{fingerprint}.md"
            report.write_bytes(b"x" * (MODULE.REPORT_MAX_BYTES + 1))
            report.chmod(0o600)

            existing = MODULE._existing_report(root, session_id, fingerprint)

        self.assertIsNone(existing)

    def test_write_report_rejects_content_over_limit_before_publication(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "report.md"
            content = "é" * (MODULE.REPORT_MAX_BYTES // 2 + 1)

            with self.assertRaisesRegex(ValueError, "byte limit"):
                MODULE._write_report(output, content, force=False)

            self.assertFalse(output.exists())
            self.assertEqual(list(output.parent.glob(f".{output.name}.*.tmp")), [])

    def test_resolve_session_rejects_ambiguous_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            session_id = "01a01979-f2da-7c00-80b2-65ee2aea9ade"
            (root / f"one-{session_id}.jsonl").write_text("{}\n", encoding="utf-8")
            (root / f"two-{session_id}.jsonl").write_text("{}\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "ambiguous"):
                MODULE._resolve_session(session_id, root)

    def test_capture_rejects_session_file_with_different_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            requested = "01a01979-f2da-7c00-80b2-65ee2aea9ade"
            rollout = root / "rollout.jsonl"
            _write_rollout(rollout, "01a00000-0000-0000-0000-000000000000")

            with self.assertRaisesRegex(ValueError, "do not match"):
                MODULE.capture_session(requested, rollout)

    def test_capture_rejects_mixed_session_identities(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            requested = "01a01979-f2da-7c00-80b2-65ee2aea9ade"
            rollout = root / "rollout.jsonl"
            records = [
                {"type": "session_meta", "payload": {"id": "01a00000-0000-0000-0000-000000000000", "cwd": "/repo"}},
                {"type": "session_meta", "payload": {"id": requested, "cwd": "/repo"}},
            ]
            rollout.write_text("".join(json.dumps(item) + "\n" for item in records), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "identities"):
                MODULE.capture_session(requested, rollout)

    def test_identical_same_second_actions_are_not_collapsed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            session_id = "01a01979-f2da-7c00-80b2-65ee2aea9ade"
            rollout = root / "rollout.jsonl"
            _write_rollout(rollout, session_id)
            records = [json.loads(line) for line in rollout.read_text(encoding="utf-8").splitlines()]
            activity = "[sub-agent] activity cli=minimax elapsed=4s event=tool:Read session=external-1\n"
            runner_output = records[-1]["payload"]["output"]
            runner_output["output"] = activity + activity + runner_output["output"]
            rollout.write_text("".join(json.dumps(item) + "\n" for item in records), encoding="utf-8")

            capture = MODULE.capture_session(session_id, rollout)

        matching = [item for item in capture.activity_timeline if item.event == "tool:Read"]
        self.assertEqual(len(matching), 3)

    def test_force_never_follows_output_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            session_id = "01a01979-f2da-7c00-80b2-65ee2aea9ade"
            rollout = root / f"rollout-{session_id}.jsonl"
            target = root / "target.md"
            output = root / "report.md"
            _write_rollout(rollout, session_id)
            target.write_text("preserve me", encoding="utf-8")
            output.symlink_to(target)

            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                exit_code = MODULE.main(
                    [
                        "--session-id",
                        session_id,
                        "--session-file",
                        str(rollout),
                        "--output",
                        str(output),
                        "--force",
                    ]
                )
            self.assertEqual(exit_code, 1)
            self.assertEqual(target.read_text(encoding="utf-8"), "preserve me")

    def test_exclusive_report_write_allows_only_one_concurrent_creator(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "report.md"
            barrier = threading.Barrier(2)
            successes: list[str] = []
            errors: list[Exception] = []

            def write(content: str) -> None:
                barrier.wait()
                try:
                    MODULE._write_report(output, content, force=False)
                    successes.append(content)
                except OSError as exc:
                    errors.append(exc)

            threads = [threading.Thread(target=write, args=(content,)) for content in ("one", "two")]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            self.assertEqual(len(successes), 1)
            self.assertEqual(len(errors), 1)
            self.assertEqual(output.read_text(encoding="utf-8"), successes[0])

    def test_force_resets_existing_report_mode_to_0600(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "report.md"
            output.write_text("old", encoding="utf-8")
            output.chmod(0o644)

            MODULE._write_report(output, "new", force=True)

            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            self.assertEqual(output.read_text(encoding="utf-8"), "new")


if __name__ == "__main__":
    unittest.main()
