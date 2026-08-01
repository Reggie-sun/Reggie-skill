#!/usr/bin/env python3
"""Validate the project-to-resume Skill structure and deterministic contracts."""

from __future__ import annotations

import argparse
import ast
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any


REQUIRED_FILES = {
    "SKILL.md",
    "agents/openai.yaml",
    "references/workflow.md",
    "references/evidence-rubric.md",
    "references/resume-writing-rules-zh.md",
    "references/output-schema.md",
    "references/confidentiality-rules.md",
    "references/jd-tailoring-rules.md",
    "assets/project-facts-template.md",
    "assets/evidence-ledger-template.md",
    "assets/resume-project-template.txt",
    "assets/interview-evidence-template.md",
    "scripts/collect_repo_evidence.py",
    "scripts/validate_skill.py",
    "evals/trigger-prompts.csv",
}

EXPECTED_MODES = {
    "Repository Audit",
    "Resume Update",
    "JD Tailoring",
    "Interview Preparation",
    "Claim Validation",
    "Not Applicable",
}

REQUIRED_STATUSES = {
    "VERIFIED_PRODUCTION",
    "VERIFIED_PILOT",
    "IMPLEMENTED",
    "SHADOW",
    "EXPERIMENTAL",
    "PLANNED",
    "PAUSED",
    "UNKNOWN",
}

REQUIRED_RESPONSIBILITIES = {"INDIVIDUAL", "PRIMARY_OWNER", "COLLABORATIVE", "UNKNOWN"}
REQUIRED_CONFIDENCE = {"HIGH", "MEDIUM", "LOW", "USER_CONFIRMATION_REQUIRED"}
REQUIRED_METRICS = {"VERIFIED", "DERIVED", "UNVERIFIED"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill_directory", nargs="?", default=Path(__file__).resolve().parents[1])
    parser.add_argument("--json", action="store_true", help="Emit machine-readable results")
    return parser.parse_args()


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    match = re.match(r"\A---\n(.*?)\n---\n(.*)\Z", text, flags=re.DOTALL)
    if not match:
        raise ValueError("SKILL.md must contain YAML frontmatter delimited by ---")
    values: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if not line.strip():
            continue
        if ":" not in line:
            raise ValueError(f"invalid frontmatter line: {line}")
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values, match.group(2)


def add(checks: list[dict[str, Any]], name: str, passed: bool, detail: str) -> None:
    checks.append({"name": name, "passed": passed, "detail": detail})


def validate(root: Path) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    root = root.expanduser().resolve()
    add(checks, "skill_directory", root.is_dir(), str(root))
    if not root.is_dir():
        return {"valid": False, "skill_directory": str(root), "checks": checks}

    missing = sorted(path for path in REQUIRED_FILES if not (root / path).is_file())
    add(checks, "required_files", not missing, "missing: " + ", ".join(missing) if missing else "all present")

    skill_path = root / "SKILL.md"
    if skill_path.is_file():
        skill_text = skill_path.read_text(encoding="utf-8")
        try:
            frontmatter, body = parse_frontmatter(skill_text)
        except ValueError as exc:
            add(checks, "frontmatter", False, str(exc))
            frontmatter, body = {}, ""
        else:
            add(checks, "frontmatter_keys", set(frontmatter) == {"name", "description"}, str(sorted(frontmatter)))
            name = frontmatter.get("name", "")
            description = frontmatter.get("description", "")
            add(checks, "name", name == "project-to-resume" and bool(re.fullmatch(r"[a-z0-9-]{1,63}", name)), name)
            add(
                checks,
                "description_trigger",
                description.startswith("Use when ") and len(description) <= 1024,
                f"length={len(description)}",
            )
            add(
                checks,
                "description_exclusions",
                "Do not use" in description
                and all(term in description for term in ("generic resume", "unrelated code", "fabricated")),
                "explicit negative trigger boundary",
            )
            add(checks, "frontmatter_size", len(match_text(frontmatter)) <= 1024, f"length={len(match_text(frontmatter))}")
        placeholder_patterns = ("[TODO", "TODO: Complete", "Structuring This Skill")
        add(
            checks,
            "no_placeholders",
            not any(pattern in skill_text for pattern in placeholder_patterns),
            "no initializer placeholder markers",
        )
        add(checks, "core_principle", "Evidence First, Resume Second" in body, "principle present")
        add(checks, "default_read_only", "Default to a read-only repository audit" in body, "read-only rule present")
        add(checks, "plain_text_output", "resume-project-zh.txt" in body, "plain-text artifact present")
    else:
        skill_text = ""

    corpus = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in root.rglob("*.md")
        if path.is_file()
    )
    for check_name, required in (
        ("implementation_statuses", REQUIRED_STATUSES),
        ("responsibility_classes", REQUIRED_RESPONSIBILITIES),
        ("confidence_classes", REQUIRED_CONFIDENCE),
        ("metrics_classes", REQUIRED_METRICS),
    ):
        missing_values = sorted(value for value in required if value not in corpus)
        add(checks, check_name, not missing_values, "missing: " + ", ".join(missing_values) if missing_values else "all present")

    template = root / "assets/resume-project-template.txt"
    if template.is_file():
        template_text = template.read_text(encoding="utf-8")
        add(
            checks,
            "plain_text_template",
            not any(line.lstrip().startswith("#") for line in template_text.splitlines())
            and "项目名称｜" in template_text
            and "技术栈：" in template_text,
            "copy-ready outer shape",
        )

    agent_yaml = root / "agents/openai.yaml"
    if agent_yaml.is_file():
        agent_text = agent_yaml.read_text(encoding="utf-8")
        add(
            checks,
            "openai_yaml",
            all(key in agent_text for key in ("display_name:", "short_description:", "default_prompt:"))
            and "$project-to-resume" in agent_text,
            "interface metadata present",
        )

    csv_path = root / "evals/trigger-prompts.csv"
    if csv_path.is_file():
        with csv_path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        fields = set(rows[0].keys()) if rows else set()
        required_fields = {"id", "should_trigger", "prompt", "expected_mode"}
        booleans_ok = all(row.get("should_trigger", "").lower() in {"true", "false"} for row in rows)
        modes_ok = all(row.get("expected_mode") in EXPECTED_MODES for row in rows)
        trigger_count = sum(row.get("should_trigger", "").lower() == "true" for row in rows)
        nontrigger_count = sum(row.get("should_trigger", "").lower() == "false" for row in rows)
        unique_ids = len({row.get("id") for row in rows}) == len(rows)
        unique_prompts = len({row.get("prompt") for row in rows}) == len(rows)
        positive_prompts = "\n".join(
            row.get("prompt", "")
            for row in rows
            if row.get("should_trigger", "").lower() == "true"
        )
        negative_prompts = "\n".join(
            row.get("prompt", "")
            for row in rows
            if row.get("should_trigger", "").lower() == "false"
        )
        boundary_coverage = (
            "Audit this repository" in positive_prompts
            and "不需要查看仓库" in negative_prompts
            and "帮我编一个" in negative_prompts
            and "只有一份 JD" in negative_prompts
        )
        add(checks, "eval_fields", required_fields.issubset(fields), str(sorted(fields)))
        add(
            checks,
            "eval_rows",
            len(rows) >= 12 and trigger_count >= 6 and nontrigger_count >= 6,
            f"rows={len(rows)}, trigger={trigger_count}, nontrigger={nontrigger_count}",
        )
        add(
            checks,
            "eval_values",
            booleans_ok and modes_ok and unique_ids and unique_prompts,
            "booleans, modes, IDs, and prompts valid",
        )
        add(
            checks,
            "eval_boundary_coverage",
            boundary_coverage,
            "English positive plus no-repository, fabrication, and JD-only negatives",
        )

    for script_name in ("collect_repo_evidence.py", "validate_skill.py"):
        path = root / "scripts" / script_name
        if path.is_file():
            try:
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except SyntaxError as exc:
                add(checks, f"syntax_{script_name}", False, str(exc))
            else:
                add(checks, f"syntax_{script_name}", True, "AST parse passed")

    valid = all(check["passed"] for check in checks)
    return {"valid": valid, "skill_directory": str(root), "checks": checks}


def match_text(frontmatter: dict[str, str]) -> str:
    return "\n".join(f"{key}: {value}" for key, value in frontmatter.items())


def main() -> int:
    args = parse_args()
    report = validate(Path(args.skill_directory))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for check in report["checks"]:
            status = "PASS" if check["passed"] else "FAIL"
            print(f"[{status}] {check['name']}: {check['detail']}")
        print("VALID" if report["valid"] else "INVALID")
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
