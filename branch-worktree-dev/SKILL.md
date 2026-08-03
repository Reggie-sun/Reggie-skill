---
name: branch-worktree-dev
description: Use when the user explicitly invokes branch-worktree-dev or wants isolated Git branch/worktree setup with repository API/backend and frontend dev servers.
---

# Branch Worktree Dev

## Overview

This skill creates an isolated Git branch/worktree, starts the local API plus frontend using repository-native commands, and now preserves existing runtimes by default while choosing new free ports and checkpoint-committing dirty source worktrees automatically. Startup is not considered complete until the script's readiness probes pass, unless `--no-wait` is explicitly used.

This is a setup-and-switch workflow, not a setup-and-keep-coding-in-main workflow: once setup succeeds, all follow-up edits, tests, and browser checks must happen from the reported worktree path.

Use the bundled script for deterministic setup:

```bash
bash ~/.codex/skills/branch-worktree-dev/scripts/start_branch_worktree_dev.sh
```

## Activation Contract

If the user explicitly names or links this skill, using the isolated worktree/runtime is the request, not an optional preparation step.

Before task-specific edits, tests, or browser checks:

1. Run the bundled script from the source repository root, or pass `--repo`.
2. If the script succeeds, treat the reported `worktree` path as the new task root and use only the reported API/frontend URLs.
3. If the script blocks or readiness fails, stop the task and report the blocker. Do not continue implementation or verification in the source worktree.
4. If the current agent/session cannot actually relocate into the reported `worktree` path, stop after setup and hand off to a new window/session rooted there. Do not keep coding in the source checkout and call it compliant skill usage.
5. If the user later says to merge into `main`, push the worktree branch to GitHub before shutting down the branch runtime; use the finish script instead of killing API/frontend early.

Do not silently fall back to:

- editing the original source worktree;
- using already-running source ports such as `3000` / `8020`;
- testing a pre-existing runtime and presenting it as the branch worktree runtime;
- manually starting lower-level services instead of the repo-native commands selected by the script.
- treating "startup command was launched" as runtime readiness; only the script's final `[OK]` plus readiness output authorizes follow-up probes.

## Workflow

1. If inside a repository, read the repo's `AGENTS.md` or equivalent local agent rules first.
2. Check whether the user's request is only setup or also runtime startup.
3. Run the script from the source repository root or pass `--repo` before changing files.
4. Switch working directory to the reported worktree before doing any requested implementation.
5. Use the generated handoff artifact and `cd_command` / `enter_worktree_command` if a new window or new agent session must take over.
6. Report the created branch, worktree path, API URL, frontend URL, and tmux/log access.

If the user asked for a code change in the same turn, do it in the reported worktree after setup. If the current execution context stays rooted in the source checkout, stop after setup and resume from the new worktree instead of editing from `main`. If setup is blocked, ask for the specific unblock only, such as a repo without a usable Git remote or a push failure during finish.

## Implementation Gate

Before the first file write, test run, or browser smoke after setup:

1. Compare the actual working directory with the reported `worktree` path.
2. If they differ, treat that as a blocker for implementation, not as a warning.
3. Resume in the new worktree and only then continue the task.

Passing setup alone does not authorize edits in the source repository root.

## Common Commands

Create a timestamped branch/worktree and start API plus frontend:

```bash
bash ~/.codex/skills/branch-worktree-dev/scripts/start_branch_worktree_dev.sh
```

Create a timestamped branch/worktree, auto-commit dirty source changes, and pick the next free ports instead of disturbing existing runtimes:

```bash
bash ~/.codex/skills/branch-worktree-dev/scripts/start_branch_worktree_dev.sh
```

Use a named branch:

```bash
bash ~/.codex/skills/branch-worktree-dev/scripts/start_branch_worktree_dev.sh --branch feature/my-task
```

Create only the branch/worktree:

```bash
bash ~/.codex/skills/branch-worktree-dev/scripts/start_branch_worktree_dev.sh --branch feature/my-task --no-start
```

Use custom startup commands when the repository has no known Make targets:

```bash
bash ~/.codex/skills/branch-worktree-dev/scripts/start_branch_worktree_dev.sh \
  --api-command 'make api-dev' \
  --frontend-command 'cd frontend && npm run dev'
```

Use a shorter or longer maximum readiness window. This is a maximum window, not a fixed sleep; the script exits as soon as API and frontend are ready:

```bash
bash ~/.codex/skills/branch-worktree-dev/scripts/start_branch_worktree_dev.sh --startup-timeout 30
```

Push the current worktree branch first, then stop the branch runtime after the user asks to merge into `main`:

```bash
bash ~/.codex/skills/branch-worktree-dev/scripts/finish_branch_worktree_dev.sh
```

## Defaults

- Repository: current Git repository, or `--repo PATH`.
- Branch: `codex/YYYYMMDD-HHMMSS-dev` unless `--branch NAME` is provided.
- Worktree: `.worktrees/<branch-slug>` under the repository root unless `--worktree PATH` is provided.
- Base: current `HEAD` unless `--base REF` is provided.
- Dirty source worktree: automatically checkpoint-committed before creating the new worktree unless `--allow-dirty` or `--no-auto-commit` is provided.
- API command: `make dev-local-api` when available, otherwise `--api-command` is required to start API.
- Frontend command: `make dev-local-frontend` when available, otherwise a `frontend/package.json` Vite fallback or `--frontend-command`.
- Port selection: `auto` scans upward from `18020` and `3100` and chooses free ports instead of stopping an existing runtime.
- Readiness wait: API probes `http://127.0.0.1:<api-port>/api/v1/health`; frontend probes `http://127.0.0.1:<frontend-port>/`; default maximum wait is `60` seconds and returns early once ready.
- Runtime process manager: detached `tmux` session when available, otherwise `setsid` / `nohup` background processes with logs and pid files.

## Safety Rules

- Do not reset, stash, or clean files.
- When the source worktree is dirty, default to creating one automatic checkpoint commit before opening the new worktree; use `--no-auto-commit` to restore the older stop-on-dirty behavior, or `--allow-dirty` only when the user explicitly wants to branch from an uncommitted state.
- Copy `.branch-runtime.local` to the new worktree only as an ignored local runtime file; never print its contents.
- For repositories with `.branch-runtime.local`, append generated local overrides for `API_PORT`, `LOCAL_API_PORT`, `FE_PORT`, `BUGFIX_FE_PORT`, `VITE_API_TARGET`, `COMPOSE_PROJECT_NAME`, and known container names so the new worktree does not collide with the main runtime or older branch runtimes that are still running.
- If a repo-specific rule says API/frontend must be started through a particular command, use that command instead of hand-running lower-level services.
- If startup or readiness fails, report the log path and the command that failed; do not declare the runtime ready.
- When the user asks to merge into `main`, do not kill the started API/frontend before the branch has been pushed successfully; use the finish script so push happens first and teardown happens last.
- The generated handoff file is part of the contract: use it to move the task into the new worktree, and treat source-worktree edits after setup as non-compliant skill usage.

## Failure Handling

When setup fails or is blocked:

- Say that branch/worktree setup did not complete.
- Include the exact failed command and the non-secret blocker.
- Do not run tests, browser smoke, or app probes against the existing source runtime as a substitute.
- Do not edit files in the source worktree to "keep going".
- Give the next command only if it requires explicit user permission or an external fix, for example rerunning with `--no-auto-commit`, choosing different startup commands, or fixing a failed `git push`.

When finishing after the user asks to merge into `main`:

- Push the worktree branch to GitHub first.
- If push fails, leave the branch runtime running and report the failure; do not shut down API/frontend.
- Only stop API/frontend after the push succeeds.

## Enterprise-grade_RAG Behavior

For `/home/reggie/vscode_folder/Enterprise-grade_RAG`, this skill should preserve the repository runtime contract:

- API startup uses `make dev-local-api`.
- Frontend startup uses `make dev-local-frontend`.
- `.branch-runtime.local` remains the runtime identity source.
- Secrets or account credentials from `.branch-runtime.local` must not be written to chat, tracked files, reports, or memory.

## Output Contract

After using the skill, say:

- branch name
- worktree path
- API URL
- frontend URL
- tmux session or log paths
- whether only setup ran or both servers were started
- handoff file and `enter_worktree_command`
- any blocker or remaining risk
- whether all subsequent work was done in the reported worktree; if not, call that out as non-compliant instead of implying the skill was followed
- when finishing, whether push succeeded before teardown and which runtime processes were stopped
