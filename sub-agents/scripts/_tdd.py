from __future__ import annotations


_TDD_CONTEXT = """## Strict TDD Contract

This task uses strict RED-GREEN-REFACTOR. Violating the order is a task failure.

1. Before editing production code, create or update the smallest test that
   reproduces the requested missing behavior.
2. Run one exact TDD command listed below and observe RED: the new test must
   fail for the intended missing behavior, not due to syntax, import, fixture,
   collection, permission, or environment errors.
3. Only after that RED evidence, make the smallest production edit needed.
4. Run the same exact TDD command and observe GREEN.
5. Refactor only while the exact command remains GREEN.

Hard boundaries:
- Observe RED before editing production code.
- Do not keep pre-RED production edits as reference, adapt them, or build tests
  around them. If this invocation inherits production edits without credible
  RED evidence, stop before further production edits and report NEEDS_CONTEXT.
- Collection, lint, type-check, or import-only success is not RED evidence.
- Do not substitute, wrap, pipe, or broaden an exact TDD command.
- If the test passes before implementation or the exact command cannot run,
  stop before production edits and report NEEDS_CONTEXT with the evidence.
- Final output must report the exact RED command and relevant expected failure,
  then the exact GREEN command and passing result. Without both, do not report
  DONE.
"""


def build_tdd_context(base_context: str, tdd_command: str) -> str:
    return (
        f"{base_context.strip()}\n\n{_TDD_CONTEXT.strip()}\n\n"
        f"### Exact TDD Command\n\n- `{tdd_command}`"
    )
