#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Ensure sibling modules import correctly when invoked via absolute path.
sys.path.insert(0, str(Path(__file__).parent))

from _builder import CLAUDE_FAMILY_CLIS, AgentInvocation  # noqa: E402
from _constants import DEFAULT_TIMEOUT_MS, SUPPORTED_CLIS_HELP  # noqa: E402
from _dialogue import (  # noqa: E402
    build_dialogue_context,
    dialogue_json_schema,
    normalize_dialogue_result,
)
from _executor import execute_agent  # noqa: E402
from _loader import (  # noqa: E402
    discover_agents,
    load_agent,
    resolve_agent_reference,
)
from _resolver import resolve_cli  # noqa: E402
from _tdd import build_tdd_context  # noqa: E402


def _print_error(error: str, exit_code: int = 1, cli: str | None = None) -> None:
    payload = {
        "result": "",
        "exit_code": exit_code,
        "transport_exit_code": 1,
        "cli_exit_code": None,
        "status": "error",
        "termination_reason": "runner_validation",
        "error": error,
    }
    if cli is not None:
        payload["cli"] = cli
    print(json.dumps(payload))


def _resolve_timeout(cli_timeout_ms: int | None, agent_timeout_ms: int | None) -> int:
    if cli_timeout_ms is not None:
        return cli_timeout_ms
    if agent_timeout_ms is not None:
        return agent_timeout_ms
    return DEFAULT_TIMEOUT_MS


def main() -> None:
    parser = argparse.ArgumentParser(description="Execute external CLI AIs as sub-agents")
    parser.add_argument("--list", action="store_true", help="List available agents")
    parser.add_argument("--agent", help="Agent definition name")
    parser.add_argument("--prompt", help="Task prompt")
    parser.add_argument("--cwd", help="Working directory (absolute path)")
    parser.add_argument("--agents-dir", help="Directory containing agent definitions")
    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help=(
            "Idle timeout in ms; overrides the agent definition "
            f"(global default: {DEFAULT_TIMEOUT_MS})"
        ),
    )
    parser.add_argument("--cli", help=f"Force specific CLI ({SUPPORTED_CLIS_HELP})")
    parser.add_argument(
        "--allow-command",
        action="append",
        default=[],
        help=(
            "Exact Bash shell string to authorize for a Claude-family safe-edit agent; "
            "preserve quoting and repeat for multiple commands"
        ),
    )
    parser.add_argument(
        "--allow-path",
        action="append",
        default=[],
        help=(
            "File or directory pattern relative to --cwd that a Claude-family "
            "safe-edit agent may edit; repeat for multiple ownership paths"
        ),
    )
    parser.add_argument(
        "--dialogue",
        action="store_true",
        help="Require the bounded multi-turn response protocol",
    )
    parser.add_argument(
        "--parent-answer-file",
        action="append",
        default=[],
        help=(
            "Prior-turn parent answer artifact inside --cwd; requires --dialogue "
            "and may be repeated"
        ),
    )
    parser.add_argument(
        "--tdd",
        action="store_true",
        help="Inject the strict RED-GREEN-REFACTOR writer contract",
    )
    parser.add_argument(
        "--tdd-command",
        action="append",
        default=[],
        help=(
            "Exact command that must demonstrate RED then GREEN; requires --tdd, "
            "must also appear as --allow-command, and must be supplied exactly once"
        ),
    )

    args = parser.parse_args()

    if args.list:
        agents, agents_dir, fallback_dir = discover_agents(
            args.agents_dir,
            args.cwd,
        )
        payload = {"agents": agents, "agents_dir": agents_dir}
        if fallback_dir is not None:
            payload["fallback_agents_dir"] = fallback_dir
        print(json.dumps(payload, ensure_ascii=False))
        sys.exit(0)

    if not args.agent:
        _print_error("Missing required argument: --agent.")
        sys.exit(1)
    if not args.prompt:
        _print_error("Missing required argument: --prompt.")
        sys.exit(1)
    if not args.cwd:
        _print_error("Missing required argument: --cwd.")
        sys.exit(1)
    if not os.path.isabs(args.cwd):
        _print_error(f"Invalid --cwd {args.cwd!r}: expected an absolute path.")
        sys.exit(1)
    if not os.path.isdir(args.cwd):
        _print_error(f"Invalid --cwd {args.cwd!r}: directory does not exist.")
        sys.exit(1)

    try:
        agents_dir, agent_name = resolve_agent_reference(
            args.agent,
            args.agents_dir,
            args.cwd,
        )
        (
            run_agent_cli,
            system_context,
            _,
            agent_file,
            permission,
            model,
            effort,
            agent_timeout_ms,
        ) = load_agent(agents_dir, agent_name)
    except (FileNotFoundError, ValueError) as e:
        _print_error(str(e))
        sys.exit(1)

    cli = args.cli or resolve_cli(run_agent_cli)
    structured_dialogue = args.dialogue and cli in CLAUDE_FAMILY_CLIS
    if args.parent_answer_file and not args.dialogue:
        _print_error("--parent-answer-file requires --dialogue.", cli=cli)
        sys.exit(1)
    if args.tdd_command and not args.tdd:
        _print_error("--tdd-command requires --tdd.", cli=cli)
        sys.exit(1)
    if args.tdd:
        if permission != "safe-edit":
            _print_error("--tdd requires a safe-edit agent definition.", cli=cli)
            sys.exit(1)
        if not args.tdd_command:
            _print_error(
                "--tdd requires exactly one --tdd-command that is also "
                "granted with --allow-command.",
                cli=cli,
            )
            sys.exit(1)
        if len(args.tdd_command) != 1:
            _print_error(
                "--tdd requires exactly one --tdd-command.",
                cli=cli,
            )
            sys.exit(1)
        tdd_command = args.tdd_command[0]
        if tdd_command not in args.allow_command:
            _print_error(
                "The --tdd-command must also be granted by an identical "
                f"--allow-command; missing: {tdd_command!r}.",
                cli=cli,
            )
            sys.exit(1)
        system_context = build_tdd_context(system_context, tdd_command)

    if args.dialogue:
        try:
            system_context = build_dialogue_context(
                system_context,
                args.cwd,
                args.parent_answer_file,
                structured_output=structured_dialogue,
            )
        except (OSError, UnicodeError, ValueError) as e:
            _print_error(str(e), cli=cli)
            sys.exit(1)

    invocation = AgentInvocation(
        cli=cli,
        prompt=args.prompt,
        cwd=args.cwd,
        system_context=system_context,
        agent_file=agent_file,
        permission=permission,
        model=model,
        effort=effort,
        allowed_commands=tuple(args.allow_command),
        allowed_paths=tuple(args.allow_path),
        structured_output_schema=(
            dialogue_json_schema() if structured_dialogue else None
        ),
    )

    try:
        result = execute_agent(
            invocation,
            timeout_ms=_resolve_timeout(args.timeout, agent_timeout_ms),
            allow_dialogue_fallback=args.dialogue,
        )
    except ValueError as e:
        _print_error(str(e), cli=cli)
        sys.exit(1)

    if args.dialogue:
        result = normalize_dialogue_result(result, args.cwd)

    print(json.dumps(result, ensure_ascii=False))
    sys.exit(result.get("transport_exit_code", 0 if result["status"] == "success" else 1))


if __name__ == "__main__":
    main()
