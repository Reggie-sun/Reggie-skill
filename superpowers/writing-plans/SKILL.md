---
name: writing-plans
description: Use when the user explicitly requests a durable implementation plan, or when approved work is Standard/Heavy, spans multiple coupled files or subsystems, or has non-obvious sequencing, ownership, migration, or rollback. Do not use for scoped Lite changes with settled acceptance criteria.
---

# Writing Plans

## Overview

Write comprehensive implementation plans assuming the engineer has zero context for our codebase and questionable taste. Document everything they need to know: which files to touch for each task, code, testing, docs they might need to check, how to test it. Give them the whole plan as bite-sized tasks. DRY. YAGNI. TDD. Frequent commits.

Assume they are a skilled developer, but know almost nothing about our toolset or problem domain. Assume they don't know good test design very well.

## Routing Gate

Classify the repository lane before creating a plan when the repository defines one. Repository rules and an explicit user request take precedence.

Use this skill when any of these is true:

- The user explicitly requests a durable implementation plan.
- Repository rules classify the approved work as Standard or Heavy.
- The work spans multiple coupled files, modules, or subsystems and requires ordered handoff.
- Ownership, migration, rollback, deployment, or verification sequencing is non-obvious.

Do not use for scoped Lite changes when all of these are true:

- The behavior and acceptance criteria are settled.
- The change is localized and follows an existing repository pattern.
- It does not alter a stable API, schema, permission, runtime configuration, or other durable contract.
- A focused test and implementation can be completed safely in one pass.

A previously written spec does not by itself require an implementation plan. If this skill was invoked automatically and the gate does not pass, return to the relevant implementation and verification discipline without creating a plan artifact.

**Announce at start:** "I'm using the writing-plans skill to create the implementation plan."

**Context:** If working in an isolated worktree, it should have been created via the `superpowers:using-git-worktrees` skill at execution time.

**Save plans to:** `docs/superpowers/plans/YYYY-MM-DD-<feature-name>.md`
- (User preferences for plan location override this default)

## Scope Check

If the spec covers multiple independent subsystems, it should have been broken into sub-project specs during brainstorming. If it wasn't, suggest breaking this into separate plans — one per subsystem. Each plan should produce working, testable software on its own.

## Output Language Contract

除非用户或仓库明确要求其它语言，每份生成的 plan 都必须遵守以下格式：

- All Markdown headings MUST be written in English, including the document title, section headings, `Task` headings, and `Step` titles.
- 正文默认使用中文，包括 Goal、Architecture、任务说明、执行说明、预期结果、风险、验收标准和 handoff 文案。
- 代码、command、path、filename、symbol、API/type name、config key、error message、log、commit message 和专有名词保留原始英文。
- 必要的工程术语可以使用英文；不要为了中文化而翻译或改写仓库中的真实 identifier。
- 标题必须是自然、具体的英文，不使用拼音或中英混合标题。
- 本契约约束生成的 plan artifact；用户和仓库的明确语言要求优先。

## File Structure

Before defining tasks, map out which files will be created or modified and what each one is responsible for. This is where decomposition decisions get locked in.

- Design units with clear boundaries and well-defined interfaces. Each file should have one clear responsibility.
- You reason best about code you can hold in context at once, and your edits are more reliable when files are focused. Prefer smaller, focused files over large ones that do too much.
- Files that change together should live together. Split by responsibility, not by technical layer.
- In existing codebases, follow established patterns. If the codebase uses large files, don't unilaterally restructure - but if a file you're modifying has grown unwieldy, including a split in the plan is reasonable.

This structure informs the task decomposition. Each task should produce self-contained changes that make sense independently.

## Bite-Sized Task Granularity

**Each step is one action (2-5 minutes):**
- "Write the failing test" - step
- "Run it to make sure it fails" - step
- "Implement the minimal code to make the test pass" - step
- "Run the tests and make sure they pass" - step
- "Commit" - step

## Plan Document Header

**Every plan MUST start with this header:**

```markdown
# [Feature Name] Implementation Plan

> **For agentic workers:** 实施本 plan 时，REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans。按 Task 顺序执行，并使用 checkbox (`- [ ]`) 跟踪进度。

**Goal:** [用一句中文说明要实现的结果]

**Architecture:** [用 2-3 句中文说明实现路径、owner 和关键边界]

**Tech Stack:** [列出技术、library 和 tool；必要名称保留英文]

---
```

## Task Structure

````markdown
### Task N: [English Component Name]

**Files:**
- Create: `exact/path/to/file.py`
- Modify: `exact/path/to/existing.py:123-145`
- Test: `tests/exact/path/to/test.py`

- [ ] **Step 1: Write the failing test**

```python
def test_specific_behavior():
    result = function(input)
    assert result == expected
```

- [ ] **Step 2: Run test to verify it fails**

运行：`pytest tests/path/test.py::test_name -v`
预期：测试因目标行为尚未实现而失败，例如 `function not defined`。

- [ ] **Step 3: Write minimal implementation**

```python
def function(input):
    return expected
```

- [ ] **Step 4: Run test to verify it passes**

运行：`pytest tests/path/test.py::test_name -v`
预期：PASS，且没有新的 warning 或非预期输出。

- [ ] **Step 5: Commit**

```bash
git add tests/path/test.py src/path/file.py
git commit -m "feat: add specific feature"
```
````

## No Placeholders

Every step must contain the actual content an engineer needs. These are **plan failures** — never write them:
- "TBD", "TODO", "implement later", "fill in details"
- "Add appropriate error handling" / "add validation" / "handle edge cases"
- "Write tests for the above" (without actual test code)
- "Similar to Task N" (repeat the code — the engineer may be reading tasks out of order)
- Steps that describe what to do without showing how (code blocks required for code steps)
- References to types, functions, or methods not defined in any task

## Remember
- Exact file paths always
- Complete code in every step — if a step changes code, show the code
- Exact commands with expected output
- DRY, YAGNI, TDD, frequent commits
- English headings, Chinese narrative content, and unchanged repository identifiers

## Self-Review

After writing the complete plan, look at the spec with fresh eyes and check the plan against it. This is a checklist you run yourself — not a subagent dispatch.

**1. Spec coverage:** Skim each section/requirement in the spec. Can you point to a task that implements it? List any gaps.

**2. Placeholder scan:** Search your plan for red flags — any of the patterns from the "No Placeholders" section above. Fix them.

**3. Type consistency:** Do the types, method signatures, and property names you used in later tasks match what you defined in earlier tasks? A function called `clearLayers()` in Task 3 but `clearFullLayers()` in Task 7 is a bug.

**4. Language contract:** Check every Markdown heading is natural English. Check narrative prose is Chinese unless English is necessary for code, commands, paths, identifiers, API/type names, errors, logs, commit messages, or established technical terms.

If you find issues, fix them inline. No need to re-review — just fix and move on. If you find a spec requirement with no task, add the task.

## Execution Handoff

After saving the plan, offer execution choice:

**"Plan 已完成并保存到 `docs/superpowers/plans/<filename>.md`。有两种执行方式：**

**1. Subagent-Driven（推荐）** - 每个 Task 使用独立 subagent，并在 Task 之间进行 review，适合并行或边界清晰的工作

**2. Inline Execution** - 在当前 session 使用 `superpowers:executing-plans` 分批执行，并设置 review checkpoint

**请选择执行方式。"**

**If Subagent-Driven chosen:**
- **REQUIRED SUB-SKILL:** Use superpowers:subagent-driven-development
- Fresh subagent per task + two-stage review
- Follow the backend and role selection in `superpowers:subagent-driven-development`:
  use the host-preferred configured external runner when available, otherwise
  use equivalent native bounded-writer and read-only-reviewer roles. Dispatches
  do not pin a model.

**If Inline Execution chosen:**
- **REQUIRED SUB-SKILL:** Use superpowers:executing-plans
- Batch execution with checkpoints for review
