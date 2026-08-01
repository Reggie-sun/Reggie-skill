#!/usr/bin/env python3
"""Collect a bounded, read-only repository evidence inventory as JSON.

The inventory deliberately avoids interpreting repository scale as resume value.
It does not read file contents, contact the network, or inspect secret stores.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterable


EXCLUDED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".vscode",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "target",
    "coverage",
    "htmlcov",
    "__pycache__",
    ".next",
    ".nuxt",
    ".turbo",
    ".cache",
    "tmp",
    "temp",
}

EXCLUDED_SUFFIXES = {
    ".7z",
    ".bin",
    ".bz2",
    ".ckpt",
    ".db",
    ".dmg",
    ".gz",
    ".iso",
    ".mdb",
    ".onnx",
    ".parquet",
    ".pth",
    ".pt",
    ".rar",
    ".safetensors",
    ".sqlite",
    ".sqlite3",
    ".tar",
    ".tgz",
    ".whl",
    ".xz",
    ".zip",
}

SENSITIVE_EXACT_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    ".npmrc",
    ".pypirc",
    "credentials",
    "credentials.json",
    "id_rsa",
    "id_ed25519",
    "secrets.yaml",
    "secrets.yml",
}

CONFIG_NAMES = {
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "go.mod",
    "cargo.toml",
    "pom.xml",
    "build.gradle",
    "dockerfile",
    "compose.yaml",
    "compose.yml",
    "docker-compose.yaml",
    "docker-compose.yml",
    "makefile",
    "justfile",
}

URL_PATTERN = re.compile(r"(?i)\b(?:https?|ssh)://\S+|\bgit@[^\s:]+:[^\s]+")
SECRET_VALUE_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret)\b\s*[:=]\s*\S+"
)


class DeadlineExceeded(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect bounded repository metadata and evidence locations as JSON."
    )
    parser.add_argument("repository", nargs="?", default=".", help="Repository path")
    parser.add_argument("--timeout", type=float, default=20.0, help="Overall timeout in seconds")
    parser.add_argument("--max-files", type=int, default=20_000, help="Maximum files to inventory")
    parser.add_argument(
        "--max-list-items", type=int, default=300, help="Maximum paths retained per evidence list"
    )
    parser.add_argument(
        "--max-commits", type=int, default=30, help="Maximum Git commit summaries retained"
    )
    parser.add_argument(
        "--max-contributors", type=int, default=30, help="Maximum contributor summaries retained"
    )
    parser.add_argument(
        "--since-ref", help="Optional Git ref used to collect incremental change metadata"
    )
    parser.add_argument("--output", type=Path, help="Explicit JSON output path; stdout by default")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow --output to replace an existing file; never enabled by default",
    )
    parser.add_argument("--compact", action="store_true", help="Emit compact JSON")
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    for field in ("max_files", "max_list_items", "max_commits", "max_contributors"):
        if getattr(args, field) <= 0:
            parser.error(f"--{field.replace('_', '-')} must be positive")
    if args.force and not args.output:
        parser.error("--force requires --output")
    return args


def sanitize_text(value: str) -> str:
    value = URL_PATTERN.sub("[URL_REDACTED]", value)
    value = SECRET_VALUE_PATTERN.sub(lambda m: f"{m.group(1)}=[REDACTED]", value)
    return value.replace("\x00", "")


def is_sensitive_path(path: Path) -> bool:
    lower_parts = [part.lower() for part in path.parts]
    name = path.name.lower()
    if name in SENSITIVE_EXACT_NAMES or name.startswith(".env."):
        return True
    return any(part in {"secrets", "credentials", ".ssh", ".gnupg"} for part in lower_parts)


def check_deadline(deadline: float) -> None:
    if time.monotonic() >= deadline:
        raise DeadlineExceeded("overall timeout reached")


def remaining_seconds(deadline: float) -> float:
    return max(0.1, deadline - time.monotonic())


def run_git(repo: Path, args: list[str], deadline: float) -> tuple[str | None, str | None]:
    check_deadline(deadline)
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=min(8.0, remaining_seconds(deadline)),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"git {' '.join(args)} unavailable: {type(exc).__name__}"
    if result.returncode != 0:
        message = sanitize_text(result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "failed")
        return None, f"git {' '.join(args)}: {message}"
    return result.stdout, None


def limited_with_meta(items: Iterable[str], maximum: int) -> tuple[list[str], bool, int]:
    result: list[str] = []
    observed = 0
    for item in items:
        observed += 1
        if len(result) < maximum:
            result.append(item)
    return result, observed > maximum, observed


def classify_path(
    relative: Path,
    buckets: dict[str, list[str]],
    bucket_counts: collections.Counter[str],
    maximum: int,
) -> None:
    posix = relative.as_posix()
    name = relative.name.lower()
    parts = {part.lower() for part in relative.parts}

    def add(bucket: str) -> None:
        bucket_counts[bucket] += 1
        if len(buckets[bucket]) < maximum:
            buckets[bucket].append(posix)

    if name.startswith("readme") or parts.intersection({"docs", "doc", "specs", "adr", "adrs", "rfcs"}):
        add("documentation")
    if (
        name.startswith("test_")
        or name.endswith(("_test.py", ".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx"))
        or parts.intersection({"test", "tests", "__tests__", "e2e"})
    ):
        add("tests")
    if name in CONFIG_NAMES or name.startswith("requirements"):
        add("key_configuration")
    if (
        name == "dockerfile"
        or name.startswith("dockerfile.")
        or "compose" in name
        or parts.intersection({"k8s", "kubernetes", "helm", "deploy", "deployment", ".github", ".gitlab"})
        or name.endswith((".service", ".tf", ".tfvars"))
    ):
        add("deployment_and_ci")
    if "benchmark" in name or "eval" in name or parts.intersection({"benchmarks", "evals", "evaluation"}):
        add("benchmarks_and_evaluations")
    if "migration" in name or parts.intersection({"migrations", "alembic"}):
        add("schema_and_migrations")


def inventory_files(
    root: Path, deadline: float, max_files: int, max_list_items: int
) -> dict[str, Any]:
    buckets: dict[str, list[str]] = collections.defaultdict(list)
    bucket_counts: collections.Counter[str] = collections.Counter()
    extensions: collections.Counter[str] = collections.Counter()
    files_seen = 0
    excluded_files = 0
    stopped_by_limit = False
    timed_out = False
    walk_errors: list[str] = []
    walk_error_count = 0

    def record_walk_error(error: OSError) -> None:
        nonlocal walk_error_count
        walk_error_count += 1
        if len(walk_errors) < max_list_items:
            walk_errors.append(sanitize_text(str(error)))

    try:
        for current, dirs, files in os.walk(
            root,
            topdown=True,
            onerror=record_walk_error,
            followlinks=False,
        ):
            check_deadline(deadline)
            dirs[:] = sorted(d for d in dirs if d not in EXCLUDED_DIRS)
            for filename in sorted(files):
                check_deadline(deadline)
                path = Path(current, filename)
                relative = path.relative_to(root)
                if is_sensitive_path(relative) or path.suffix.lower() in EXCLUDED_SUFFIXES:
                    excluded_files += 1
                    continue
                files_seen += 1
                if files_seen > max_files:
                    stopped_by_limit = True
                    break
                suffix = path.suffix.lower() or "[no-extension]"
                extensions[suffix] += 1
                classify_path(relative, buckets, bucket_counts, max_list_items)
            if stopped_by_limit:
                break
    except DeadlineExceeded:
        timed_out = True

    return {
        "files_inventoried": min(files_seen, max_files),
        "excluded_files": excluded_files,
        "stopped_by_file_limit": stopped_by_limit,
        "timed_out": timed_out,
        "walk_errors": walk_errors,
        "walk_errors_observed": walk_error_count,
        "walk_errors_truncated": walk_error_count > len(walk_errors),
        "content_bytes_read": 0,
        "file_type_counts": dict(sorted(extensions.items(), key=lambda pair: (-pair[1], pair[0]))),
        "evidence_locations": {key: sorted(value) for key, value in sorted(buckets.items())},
        "evidence_location_counts": dict(sorted(bucket_counts.items())),
        "evidence_locations_truncated": {
            key: bucket_counts[key] > len(buckets[key]) for key in sorted(bucket_counts)
        },
    }


def parse_name_status(
    output: str | None, maximum: int
) -> tuple[list[dict[str, str]], bool, int]:
    if not output:
        return [], False, 0
    changes: list[dict[str, str]] = []
    observed = 0
    for line in output.splitlines():
        observed += 1
        parts = line.split("\t")
        if len(parts) >= 2 and len(changes) < maximum:
            changes.append(
                {
                    "status": sanitize_text(parts[0]),
                    "path": sanitize_text(" -> ".join(parts[1:])),
                }
            )
    return changes, observed > maximum, observed


def collect_git(
    repo: Path,
    deadline: float,
    max_commits: int,
    max_contributors: int,
    max_list_items: int,
    since_ref: str | None,
) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []

    def command(args: list[str]) -> str | None:
        output, error = run_git(repo, args, deadline)
        if error:
            warnings.append(error)
        return output

    inside = command(["rev-parse", "--is-inside-work-tree"])
    if not inside or inside.strip() != "true":
        return {"available": False}, warnings

    root_output = command(["rev-parse", "--show-toplevel"])
    branch = command(["branch", "--show-current"])
    head = command(["rev-parse", "HEAD"])
    status = command(["status", "--short", "--untracked-files=normal"])
    commits = command(
        [
            "log",
            f"--max-count={max_commits + 1}",
            "--date=short",
            "--pretty=format:%h%x09%ad%x09%s",
        ]
    )
    contributors = command(["shortlog", "-sn", "--all", "--no-merges"])
    unstaged = command(["diff", "--name-status"])
    staged = command(["diff", "--cached", "--name-status"])

    commit_rows: list[dict[str, str]] = []
    commit_lines = commits.splitlines() if commits else []
    if commit_lines:
        for line in commit_lines[:max_commits]:
            parts = line.split("\t", 2)
            if len(parts) == 3:
                commit_rows.append(
                    {"hash": parts[0], "date": parts[1], "subject": sanitize_text(parts[2])}
                )

    contributor_rows: list[dict[str, Any]] = []
    contributor_lines = contributors.splitlines() if contributors else []
    if contributor_lines:
        for line in contributor_lines[:max_contributors]:
            match = re.match(r"\s*(\d+)\s+(.+)$", line)
            if match:
                contributor_rows.append(
                    {"commit_count": int(match.group(1)), "display_name": sanitize_text(match.group(2))}
                )

    incremental: dict[str, Any] | None = None
    if since_ref:
        check = command(["rev-parse", "--verify", f"{since_ref}^{{commit}}"])
        if check:
            delta = command(["diff", "--name-status", f"{since_ref}..HEAD"])
            delta_log = command(
                [
                    "log",
                    f"--max-count={max_commits + 1}",
                    "--date=short",
                    "--pretty=format:%h%x09%ad%x09%s",
                    f"{since_ref}..HEAD",
                ]
            )
            delta_changes, delta_truncated, delta_count = parse_name_status(
                delta, max_list_items
            )
            delta_commit_rows, delta_commits_truncated, delta_commit_count = limited_with_meta(
                (sanitize_text(line) for line in (delta_log or "").splitlines()),
                max_commits,
            )
            incremental = {
                "since_ref": since_ref,
                "resolved_ref": check.strip(),
                "changed_files": delta_changes,
                "changed_files_observed": delta_count,
                "changed_files_truncated": delta_truncated,
                "commit_summaries": delta_commit_rows,
                "commit_summaries_observed": delta_commit_count,
                "commit_summaries_truncated": delta_commits_truncated,
            }
        else:
            incremental = {"since_ref": since_ref, "error": "ref could not be resolved"}

    status_rows, status_truncated, status_count = limited_with_meta(
        (sanitize_text(line) for line in (status or "").splitlines()), max_list_items
    )
    unstaged_rows, unstaged_truncated, unstaged_count = parse_name_status(
        unstaged, max_list_items
    )
    staged_rows, staged_truncated, staged_count = parse_name_status(staged, max_list_items)
    if status_truncated or unstaged_truncated or staged_truncated:
        warnings.append("One or more Git change lists reached --max-list-items and are partial")
    if len(commit_lines) > max_commits:
        warnings.append("Commit summaries reached --max-commits and are partial")
    if len(contributor_lines) > max_contributors:
        warnings.append("Contributor summaries reached --max-contributors and are partial")
    if incremental and any(
        incremental.get(key) is True
        for key in ("changed_files_truncated", "commit_summaries_truncated")
    ):
        warnings.append("Incremental Git evidence reached a configured limit and is partial")

    return (
        {
            "available": True,
            "repository_root": (root_output or "").strip(),
            "branch": (branch or "").strip() or "DETACHED_OR_UNKNOWN",
            "head": (head or "").strip() or None,
            "worktree_status": status_rows,
            "worktree_status_observed": status_count,
            "worktree_status_truncated": status_truncated,
            "unstaged_changes": unstaged_rows,
            "unstaged_changes_observed": unstaged_count,
            "unstaged_changes_truncated": unstaged_truncated,
            "staged_changes": staged_rows,
            "staged_changes_observed": staged_count,
            "staged_changes_truncated": staged_truncated,
            "commit_summaries": commit_rows,
            "commit_summaries_observed": len(commit_lines),
            "commit_summaries_truncated": len(commit_lines) > max_commits,
            "contributor_summary": contributor_rows,
            "contributor_summary_observed": len(contributor_lines),
            "contributor_summary_truncated": len(contributor_lines) > max_contributors,
            "contributor_caution": "Commit counts and names do not prove the user's identity or ownership.",
            "incremental": incremental,
        },
        warnings,
    )


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    deadline = started + args.timeout
    requested = Path(args.repository).expanduser().resolve()
    if not requested.exists() or not requested.is_dir():
        raise ValueError(f"repository directory does not exist: {requested}")

    git_data, warnings = collect_git(
        requested,
        deadline,
        args.max_commits,
        args.max_contributors,
        args.max_list_items,
        args.since_ref,
    )
    root = Path(git_data.get("repository_root") or requested).resolve()
    if not root.exists() or not root.is_dir():
        root = requested
        warnings.append("Git root was unavailable; used the requested directory")

    inventory = inventory_files(root, deadline, args.max_files, args.max_list_items)
    if inventory["timed_out"]:
        warnings.append("File inventory reached the overall timeout and is partial")
    if inventory["stopped_by_file_limit"]:
        warnings.append("File inventory reached --max-files and is partial")
    if inventory["walk_errors"]:
        warnings.append("One or more directories could not be inventoried; see inventory.walk_errors")
    truncated_categories = sorted(
        key
        for key, truncated in inventory["evidence_locations_truncated"].items()
        if truncated
    )
    if truncated_categories:
        warnings.append(
            "Evidence path lists reached --max-list-items and are partial: "
            + ", ".join(truncated_categories)
        )

    return {
        "schema_version": "1.0",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "repository": {
            "name": root.name,
            "root": str(root),
            "requested_path": str(requested),
        },
        "limits": {
            "timeout_seconds": args.timeout,
            "max_files": args.max_files,
            "max_list_items": args.max_list_items,
            "max_commits": args.max_commits,
            "max_contributors": args.max_contributors,
            "elapsed_seconds": round(time.monotonic() - started, 3),
        },
        "safety": {
            "network_accessed": False,
            "application_file_contents_opened_directly": False,
            "file_contents_emitted": False,
            "secret_file_contents_read": False,
            "secret_paths_skipped": True,
            "large_binary_database_weight_and_build_artifacts_skipped": True,
            "business_value_interpreted": False,
        },
        "git": git_data,
        "inventory": inventory,
        "warnings": warnings,
        "interpretation_notice": (
            "Counts and paths are inventory evidence only; they do not prove business value, "
            "deployment status, quality, or personal ownership."
        ),
    }


def main() -> int:
    args = parse_args()
    output: Path | None = args.output.expanduser().resolve() if args.output else None
    if output and output.exists() and not args.force:
        print(
            json.dumps(
                {
                    "error": f"output already exists: {output}",
                    "hint": "Choose a new path or pass --force explicitly.",
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 3
    try:
        report = build_report(args)
    except (ValueError, DeadlineExceeded) as exc:
        print(json.dumps({"error": str(exc), "partial": False}, ensure_ascii=False), file=sys.stderr)
        return 2

    indent = None if args.compact else 2
    rendered = json.dumps(report, ensure_ascii=False, indent=indent, sort_keys=False) + "\n"
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        mode = "w" if args.force else "x"
        try:
            with output.open(mode, encoding="utf-8") as handle:
                handle.write(rendered)
        except FileExistsError:
            print(
                json.dumps(
                    {
                        "error": f"output appeared during collection: {output}",
                        "hint": "Choose a new path or rerun with --force explicitly.",
                    },
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            return 3
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
