from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from _constants import SUPPORTED_CLIS_HELP, format_concatenated_prompt
from _loader import DEFAULT_PERMISSION


@dataclass(frozen=True)
class AgentInvocation:
    cli: str
    prompt: str
    cwd: str
    system_context: str = ""
    agent_file: str | None = None
    permission: str = DEFAULT_PERMISSION
    model: str | None = None
    effort: str | None = None
    allowed_commands: tuple[str, ...] = ()
    allowed_paths: tuple[str, ...] = ()


def build_command(cli: str, prompt: str) -> tuple[str, list]:
    if cli == "codex":
        return "codex", ["exec", "--json", "--skip-git-repo-check", prompt]

    if cli in ("claude", "glm", "kimi", "minimax"):
        # GLM, Kimi, and MiniMax use Claude CLI as their transport.
        return "claude", ["--output-format", "stream-json", "--verbose", "-p", prompt]

    if cli == "gemini":
        # Headless Gemini otherwise prompts for folder trust.
        return "gemini", ["--skip-trust", "--output-format", "stream-json", "-p", prompt]

    if cli == "grok":
        return "grok", [
            "--output-format",
            "json",
            "--verbatim",
            "-p",
            prompt,
        ]

    if cli == "opencode":
        return "opencode", ["run", "--format", "json", "--auto", prompt]

    if cli == "cursor-agent":
        # Cursor credentials stay out of argv.
        return "cursor-agent", ["--output-format", "json", "-p", prompt]

    raise ValueError(f"Unsupported CLI {cli!r}. Choose one of: {SUPPORTED_CLIS_HELP}.")


_CLAUDE_READ_ONLY_FLAGS = [
    "--permission-mode",
    "dontAsk",
    "--tools",
    "Read,Glob,Grep",
    "--disallowedTools",
    "Write,Edit,NotebookEdit,EnterPlanMode,ExitPlanMode,Task,Bash,mcp__*",
    "--mcp-config",
    '{"mcpServers":{}}',
    "--strict-mcp-config",
    "--no-session-persistence",
    "--setting-sources",
    "",
]

_CLAUDE_SAFE_EDIT_FLAGS = [
    "--permission-mode",
    "dontAsk",
    "--tools",
    "Read,Glob,Grep,Write,Edit",
    "--disallowedTools",
    "NotebookEdit,EnterPlanMode,ExitPlanMode,Task,Agent,WebFetch,WebSearch,mcp__*",
    "--mcp-config",
    '{"mcpServers":{}}',
    "--strict-mcp-config",
    "--no-session-persistence",
    "--setting-sources",
    "",
]


_PERMISSION_MAPPING = {
    "codex": {
        "read-only": ["-s", "read-only"],
        "safe-edit": ["-s", "workspace-write", "-c", "approval_policy=never"],
        "yolo": ["--dangerously-bypass-approvals-and-sandbox"],
    },
    "claude": {
        "read-only": _CLAUDE_READ_ONLY_FLAGS,
        "safe-edit": _CLAUDE_SAFE_EDIT_FLAGS,
        "yolo": ["--dangerously-skip-permissions"],
    },
    "gemini": {
        "read-only": ["--approval-mode", "plan"],
        "safe-edit": ["--approval-mode", "auto_edit"],
        "yolo": ["-y"],
    },
    "cursor-agent": {
        "read-only": ["--mode", "plan"],
        "safe-edit": ["--trust"],
        "yolo": ["-f", "--trust"],
    },
    # Grok enforces these levels through sandbox profiles.
    "grok": {
        "read-only": ["--permission-mode", "bypassPermissions", "--sandbox", "read-only"],
        "safe-edit": ["--permission-mode", "bypassPermissions", "--sandbox", "workspace"],
        "yolo": ["--permission-mode", "bypassPermissions", "--sandbox", "off"],
    },
    # OpenCode permissions are supplied through OPENCODE_PERMISSION.
    "opencode": {
        "read-only": [],
        "safe-edit": [],
        "yolo": [],
    },
}

_PERMISSION_MAPPING["glm"] = _PERMISSION_MAPPING["claude"]
_PERMISSION_MAPPING["kimi"] = _PERMISSION_MAPPING["claude"]
_PERMISSION_MAPPING["minimax"] = _PERMISSION_MAPPING["claude"]


def permission_flags(cli: str, permission: str) -> list:
    try:
        return list(_PERMISSION_MAPPING[cli][permission])
    except KeyError as e:
        raise ValueError(f"No permission mapping for cli={cli!r}, permission={permission!r}") from e


_EFFORT_SUPPORTED_CLIS = frozenset(
    {"codex", "claude", "glm", "kimi", "minimax", "grok", "opencode"}
)
_EFFORT_UNSUPPORTED_CLIS = frozenset({"cursor-agent", "gemini"})


def effort_flags(cli: str, effort: str | None) -> list:
    if not effort:
        return []

    if cli == "codex":
        # JSON encoding produces a safe TOML string for the config override.
        encoded_effort = json.dumps(effort, ensure_ascii=False)
        return ["-c", f"model_reasoning_effort={encoded_effort}"]
    if cli in ("claude", "glm", "kimi", "minimax"):
        return ["--effort", effort]
    if cli == "grok":
        return ["--reasoning-effort", effort]
    if cli == "opencode":
        return ["--variant", effort]
    if cli in _EFFORT_UNSUPPORTED_CLIS:
        supported = ", ".join(sorted(_EFFORT_SUPPORTED_CLIS))
        raise ValueError(
            f"Effort is available for: {supported}; selected backend: {cli!r}. "
            "Remove effort or select a listed backend."
        )
    raise ValueError(f"Unsupported CLI {cli!r}. Choose one of: {SUPPORTED_CLIS_HELP}.")


def _invocation_flags(inv: AgentInvocation) -> list:
    flags = permission_flags(inv.cli, inv.permission)
    claude_family = inv.cli in ("claude", "glm", "kimi", "minimax")
    if inv.permission == "safe-edit" and claude_family and not inv.allowed_paths:
        raise ValueError(
            "Claude-family safe-edit requires at least one explicit --allow-path."
        )
    if inv.allowed_commands or inv.allowed_paths:
        if inv.permission != "safe-edit" or not claude_family:
            raise ValueError(
                "Explicit allowed commands and paths require a Claude-family safe-edit invocation."
            )
        allowed_rules = []
        cwd = Path(inv.cwd).resolve()
        for allowed_path in inv.allowed_paths:
            relative = Path(allowed_path)
            if (
                not allowed_path.strip()
                or relative.is_absolute()
                or ".." in relative.parts
                or any(char in allowed_path for char in ("\n", "\r", ")"))
            ):
                raise ValueError(
                    f"Invalid allowed path {allowed_path!r}: use a non-empty path relative "
                    "to the working directory without '..' or ')'."
                )
            resolved = (cwd / relative).resolve()
            if not resolved.is_relative_to(cwd):
                raise ValueError(
                    f"Invalid allowed path {allowed_path!r}: path resolves outside the "
                    "working directory."
                )
            allowed_rules.append(f"Edit({relative.as_posix()})")
        for command in inv.allowed_commands:
            if not command.strip() or any(char in command for char in ("\n", "\r", ")")):
                raise ValueError(
                    f"Invalid allowed command {command!r}: commands must be non-empty single lines "
                    "without ')'."
                )
            allowed_rules.append(f"Bash({command})")
        if inv.allowed_commands:
            flags[flags.index("--tools") + 1] += ",Bash"
        flags.extend(["--allowedTools", *allowed_rules])
    if inv.model:
        flags.extend(["--model", inv.model])
    flags.extend(effort_flags(inv.cli, inv.effort))
    return flags


def _concatenated_args(
    inv: AgentInvocation, perm_flags: list, env: dict | None
) -> tuple[str, list, dict | None]:
    formatted_prompt = format_concatenated_prompt(inv.system_context, inv.prompt)
    command, base_args = build_command(inv.cli, formatted_prompt)
    return command, perm_flags + base_args, env


def _claude_system_prompt(inv: AgentInvocation) -> str:
    sections = [f"cwd: {inv.cwd}", inv.system_context]
    if inv.permission == "safe-edit":
        writable_paths = "\n".join(f"- {path}" for path in inv.allowed_paths)
        if inv.allowed_commands:
            bash_commands = "\n".join(f"- {command}" for command in inv.allowed_commands)
            bash_grants = (
                f"Exact Bash commands:\n{bash_commands}\n"
                "Only these exact Bash commands are authorized; do not alter, wrap, or "
                "combine them. A denial for any other command does not mean Bash is "
                "unavailable."
            )
        else:
            bash_grants = "Exact Bash commands:\n- None. Bash is not exposed."
        sections.append(
            "Runner-enforced safe-edit grants (authoritative):\n"
            f"Writable paths:\n{writable_paths}\n"
            f"{bash_grants}"
        )
    return "\n\n".join(section for section in sections if section)


def _build_claude_args(inv: AgentInvocation) -> tuple[str, list, dict | None]:
    perm = _invocation_flags(inv)
    system_prompt = _claude_system_prompt(inv)
    command, base_args = build_command(inv.cli, inv.prompt)
    return command, perm + ["--append-system-prompt", system_prompt] + base_args, None


def _build_gemini_args(inv: AgentInvocation) -> tuple[str, list, dict | None]:
    perm = _invocation_flags(inv)
    if inv.agent_file:
        command, base_args = build_command(inv.cli, inv.prompt)
        return command, perm + base_args, {"GEMINI_SYSTEM_MD": inv.agent_file}
    return _concatenated_args(inv, perm, env=None)


def _build_codex_args(inv: AgentInvocation) -> tuple[str, list, dict | None]:
    perm = _invocation_flags(inv)
    return _concatenated_args(inv, perm, env=None)


def _build_grok_args(inv: AgentInvocation) -> tuple[str, list, dict | None]:
    perm = _invocation_flags(inv)
    formatted_prompt = format_concatenated_prompt(inv.system_context, inv.prompt)
    command, base_args = build_command(inv.cli, formatted_prompt)
    return command, perm + ["--cwd", inv.cwd] + base_args, None


_OPENCODE_PERMISSION_MAPPING = {
    "read-only": {
        "edit": "deny",
        "bash": "deny",
        "task": "deny",
        "external_directory": "deny",
        "question": "deny",
    },
    "safe-edit": {
        "edit": "allow",
        "bash": "allow",
        "task": "deny",
        "external_directory": "deny",
        "question": "deny",
    },
    "yolo": "allow",
}


def _build_opencode_args(inv: AgentInvocation) -> tuple[str, list, dict | None]:
    perm = _invocation_flags(inv)
    formatted_prompt = format_concatenated_prompt(inv.system_context, inv.prompt)
    command, base_args = build_command(inv.cli, formatted_prompt)
    env_override = {"OPENCODE_PERMISSION": json.dumps(_OPENCODE_PERMISSION_MAPPING[inv.permission])}
    return command, perm + base_args, env_override


_GLM_BASE_URL = "https://api.z.ai/api/anthropic"
_KIMI_BASE_URL = "https://api.kimi.com/coding/"
_MINIMAX_BASE_URL = "https://api.minimax.io/anthropic"
_MINIMAX_MAINLAND_BASE_URL = "https://api.minimaxi.com/anthropic"
_MINIMAX_DEFAULT_MODEL = "MiniMax-M3"
_DEFAULT_CREDENTIALS_FILE = Path.home() / ".config" / "sub-agents" / "credentials.env"


def _load_saved_credentials() -> dict[str, str]:
    configured_path = os.environ.get("SUB_AGENTS_CREDENTIALS_FILE", "").strip()
    path = Path(configured_path).expanduser() if configured_path else _DEFAULT_CREDENTIALS_FILE

    try:
        file_stat = path.stat()
    except FileNotFoundError:
        return {}
    except OSError as exc:
        raise ValueError(f"Unable to inspect sub-agents credentials file {str(path)!r}: {exc}") from exc

    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Sub-agents credentials path {str(path)!r} must be a regular file.")
    if file_stat.st_uid != os.getuid() or file_stat.st_mode & 0o077:
        raise ValueError(
            f"Sub-agents credentials file {str(path)!r} must be owned by the current user "
            "and inaccessible to group and other users (mode 600 or stricter)."
        )

    credentials: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValueError(f"Unable to read sub-agents credentials file {str(path)!r}: {exc}") from exc

    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(
                f"Invalid credentials entry at {str(path)!r}:{line_number}; expected NAME=VALUE."
            )
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip()
        if name and value:
            credentials[name] = value
    return credentials


def _resolve_api_key(primary_env: str) -> str | None:
    """Resolve a provider key from the environment, then the protected credentials file."""
    for env_name in (primary_env, "CLI_API_KEY"):
        api_key = os.environ.get(env_name)
        if api_key and api_key.strip():
            return api_key

    saved_credentials = _load_saved_credentials()
    for env_name in (primary_env, "CLI_API_KEY"):
        api_key = saved_credentials.get(env_name)
        if api_key and api_key.strip():
            return api_key
    return None


def _build_redirected_claude_args(
    inv: AgentInvocation,
    api_key: str,
    base_url: str,
    credential_env: str,
) -> tuple[str, list, dict | None]:
    perm = _invocation_flags(inv)
    system_prompt = _claude_system_prompt(inv)
    command, base_args = build_command(inv.cli, inv.prompt)
    env_override = {
        "ANTHROPIC_BASE_URL": base_url,
        "ANTHROPIC_API_KEY": None,
        "ANTHROPIC_AUTH_TOKEN": None,
    }
    env_override[credential_env] = api_key
    return command, perm + ["--system-prompt", system_prompt] + base_args, env_override


def _build_glm_args(inv: AgentInvocation) -> tuple[str, list, dict | None]:
    """Route a Claude CLI invocation to Z.ai for GLM."""
    api_key = _resolve_api_key("GLM_API_KEY")
    if api_key is None:
        raise ValueError(
            "GLM configuration error: GLM_API_KEY and CLI_API_KEY are unset or blank. "
            "A Z.ai API token is required before retrying."
        )
    return _build_redirected_claude_args(inv, api_key, _GLM_BASE_URL, "ANTHROPIC_AUTH_TOKEN")


def _build_kimi_args(inv: AgentInvocation) -> tuple[str, list, dict | None]:
    """Route a Claude CLI invocation to Kimi Code."""
    api_key = _resolve_api_key("KIMI_API_KEY")
    if api_key is None:
        raise ValueError(
            "Kimi configuration error: KIMI_API_KEY and CLI_API_KEY are unset or blank. "
            "A Kimi API key is required before retrying."
        )
    return _build_redirected_claude_args(inv, api_key, _KIMI_BASE_URL, "ANTHROPIC_API_KEY")


def _build_minimax_args(inv: AgentInvocation) -> tuple[str, list, dict | None]:
    """Route a Claude CLI invocation to MiniMax's Anthropic-compatible API."""
    api_key = _resolve_api_key("MINIMAX_API_KEY")
    if api_key is None:
        raise ValueError(
            "MiniMax configuration error: MINIMAX_API_KEY and CLI_API_KEY are unset or blank. "
            "A MiniMax API key is required before retrying."
        )

    configured_base_url = os.environ.get("MINIMAX_BASE_URL", "").strip()
    if configured_base_url:
        base_url = configured_base_url
    elif api_key.startswith("sk-cp-"):
        # MiniMax Coding Plan keys are issued for the Mainland endpoint.
        base_url = _MINIMAX_MAINLAND_BASE_URL
    else:
        base_url = _MINIMAX_BASE_URL
    model = os.environ.get("MINIMAX_MODEL", "").strip() or _MINIMAX_DEFAULT_MODEL
    command, args, env_override = _build_redirected_claude_args(
        inv, api_key, base_url, "ANTHROPIC_AUTH_TOKEN"
    )
    env_override.update(
        {
            "ANTHROPIC_MODEL": model,
            "ANTHROPIC_DEFAULT_SONNET_MODEL": model,
            "ANTHROPIC_DEFAULT_OPUS_MODEL": model,
            "ANTHROPIC_DEFAULT_HAIKU_MODEL": model,
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        }
    )
    return command, args, env_override


def _build_cursor_args(inv: AgentInvocation) -> tuple[str, list, dict | None]:
    perm = _invocation_flags(inv)
    # Keep the credential out of argv; logged-in sessions need no override.
    api_key = _resolve_api_key("CURSOR_API_KEY")
    env_override = {"CURSOR_API_KEY": api_key} if api_key else None
    return _concatenated_args(inv, perm, env=env_override)


_BUILDERS = {
    "claude": _build_claude_args,
    "gemini": _build_gemini_args,
    "codex": _build_codex_args,
    "cursor-agent": _build_cursor_args,
    "glm": _build_glm_args,
    "kimi": _build_kimi_args,
    "minimax": _build_minimax_args,
    "grok": _build_grok_args,
    "opencode": _build_opencode_args,
}


def build_invocation_args(inv: AgentInvocation) -> tuple[str, list, dict | None]:
    try:
        builder = _BUILDERS[inv.cli]
    except KeyError as e:
        raise ValueError(
            f"Unsupported CLI {inv.cli!r}. Choose one of: {SUPPORTED_CLIS_HELP}."
        ) from e
    return builder(inv)
