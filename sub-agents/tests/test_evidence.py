from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from _evidence import normalize_required_evidence_paths  # noqa: E402


class RequiredEvidencePathTests(unittest.TestCase):
    def test_paths_are_normalized_and_deduplicated_in_declared_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "schema").mkdir()
            owner = root / "owner.py"
            validator = root / "schema" / "validator.py"
            owner.write_text("OWNER = True\n", encoding="utf-8")
            validator.write_text("VALID = True\n", encoding="utf-8")

            normalized = normalize_required_evidence_paths(
                temp_dir,
                [str(owner), "schema/validator.py", "owner.py"],
            )

        self.assertEqual(normalized, ("owner.py", "schema/validator.py"))

    def test_outside_missing_and_symlink_paths_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            outside = root.parent / f"{root.name}-outside.py"
            outside.write_text("OUTSIDE = True\n", encoding="utf-8")
            link = root / "link.py"
            link.symlink_to(outside)
            try:
                cases = (
                    (str(outside), "outside"),
                    ("missing.py", "existing regular file"),
                    ("link.py", "symlink"),
                )
                for value, error in cases:
                    with self.subTest(value=value):
                        with self.assertRaisesRegex(ValueError, error):
                            normalize_required_evidence_paths(temp_dir, [value])
            finally:
                outside.unlink()


if __name__ == "__main__":
    unittest.main()
