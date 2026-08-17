from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SDD_DIR = REPO_ROOT / "superpowers" / "subagent-driven-development"


class MiniMaxSddRoutingTests(unittest.TestCase):
    def test_external_explorer_writer_and_native_reviewer_are_explicit(self) -> None:
        skill = (SDD_DIR / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("MiniMax external as the primary backend", skill)
        self.assertIn("external `explorer`", skill)
        self.assertIn("external `writer` for implementation and fix rounds", skill)
        self.assertIn("native named `reviewer` profile for every review gate", skill)

    def test_writer_has_structured_path_command_and_commit_boundaries(self) -> None:
        skill = (SDD_DIR / "SKILL.md").read_text(encoding="utf-8")
        implementer = (SDD_DIR / "implementer-prompt.md").read_text(encoding="utf-8")

        self.assertIn("--allow-path", skill)
        self.assertIn("--allow-command", skill)
        self.assertIn("git commit --only", skill)
        self.assertIn("git commit --only", implementer)

    def test_all_review_templates_use_native_reviewer(self) -> None:
        for filename in ("task-reviewer-prompt.md", "re-review-prompt.md"):
            with self.subTest(filename=filename):
                content = (SDD_DIR / filename).read_text(encoding="utf-8")
                self.assertIn("native named `reviewer` profile", content)
                self.assertIn("agent_type: reviewer", content)

        self.assertFalse((SDD_DIR / "spec-reviewer-prompt.md").exists())
        self.assertFalse((SDD_DIR / "code-quality-reviewer-prompt.md").exists())


if __name__ == "__main__":
    unittest.main()
