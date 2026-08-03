#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  finish_branch_worktree_dev.sh [options]

Push the current worktree branch to GitHub first, then stop the runtime that
branch-worktree-dev started for that worktree.

Options:
  --repo PATH              Git worktree to finish. Defaults to current repo.
  --branch NAME            Branch to push. Defaults to current branch.
  --remote NAME            Git remote to push to. Defaults to origin.
  --no-push                Skip the push step and only stop the runtime.
  --skip-api-stop          Do not stop the API runtime.
  --skip-frontend-stop     Do not stop the frontend runtime.
  -h, --help               Show this help.

Examples:
  finish_branch_worktree_dev.sh
  finish_branch_worktree_dev.sh --remote upstream
USAGE
}

die() {
  printf '[FAIL] %s\n' "$*" >&2
  exit 1
}

info() {
  printf '[INFO] %s\n' "$*"
}

filtered_status_output() {
  git status --porcelain --untracked-files=all \
    | grep -Ev '^\?\? (\.codex($|/)|\.worktrees($|/)|frontend/node_modules($|/)|\.branch-runtime\.local$|\.env$)' \
    || true
}

has_make_target() {
  local root="$1"
  local target="$2"
  [[ -f "${root}/Makefile" ]] || return 1
  grep -Eq "^${target}:" "${root}/Makefile"
}

kill_pid_file() {
  local label="$1"
  local pid_file="$2"

  [[ -f "${pid_file}" ]] || return 0
  local pid
  pid="$(cat "${pid_file}")"
  [[ -n "${pid}" ]] || return 0

  if kill -0 "${pid}" >/dev/null 2>&1; then
    kill "${pid}"
    info "stopped ${label}; pid=${pid}"
  else
    info "${label} pid file exists but process is already gone: ${pid}"
  fi

  rm -f "${pid_file}"
}

REPO=""
BRANCH=""
REMOTE_NAME="origin"
DO_PUSH=1
STOP_API=1
STOP_FRONTEND=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      REPO="${2:-}"
      shift 2
      ;;
    --branch)
      BRANCH="${2:-}"
      shift 2
      ;;
    --remote)
      REMOTE_NAME="${2:-}"
      shift 2
      ;;
    --no-push)
      DO_PUSH=0
      shift
      ;;
    --skip-api-stop)
      STOP_API=0
      shift
      ;;
    --skip-frontend-stop)
      STOP_FRONTEND=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown option: $1"
      ;;
  esac
done

if [[ -z "${REPO}" ]]; then
  REPO="$(git rev-parse --show-toplevel 2>/dev/null)" || die "not inside a Git repository; pass --repo PATH"
fi

REPO="$(cd "${REPO}" && pwd)"
cd "${REPO}"

[[ -d .git || -f .git ]] || die "not a Git worktree: ${REPO}"

STATUS_OUTPUT="$(filtered_status_output)"
if [[ -n "${STATUS_OUTPUT}" ]]; then
  printf '%s\n' "${STATUS_OUTPUT}" >&2
  die "worktree is dirty; commit or stash intentionally before push-and-stop so teardown does not hide local changes"
fi

if [[ -z "${BRANCH}" ]]; then
  BRANCH="$(git rev-parse --abbrev-ref HEAD)"
fi

if [[ "${DO_PUSH}" -eq 1 ]]; then
  git remote get-url "${REMOTE_NAME}" >/dev/null 2>&1 || die "git remote not found: ${REMOTE_NAME}"
  info "pushing ${BRANCH} to ${REMOTE_NAME} before stopping runtime"
  git push -u "${REMOTE_NAME}" "${BRANCH}"
fi

LOG_DIR="${REPO}/.codex/dev-runtime"
METADATA_FILE="${LOG_DIR}/runtime.env"
SESSION_NAME=""
START_API=0
START_FRONTEND=0
API_PID_FILE="${LOG_DIR}/api.pid"
FRONTEND_PID_FILE="${LOG_DIR}/frontend.pid"

if [[ -f "${METADATA_FILE}" ]]; then
  # shellcheck disable=SC1090
  source "${METADATA_FILE}"
fi

if [[ "${STOP_API}" -eq 1 && "${START_API}" -eq 1 ]]; then
  if has_make_target "${REPO}" "dev-local-api-stop"; then
    info "stopping API with repo-native command make dev-local-api-stop"
    make dev-local-api-stop
  else
    kill_pid_file "API" "${API_PID_FILE}"
  fi
fi

if [[ "${STOP_FRONTEND}" -eq 1 && "${START_FRONTEND}" -eq 1 ]]; then
  kill_pid_file "frontend" "${FRONTEND_PID_FILE}"
fi

if [[ -n "${SESSION_NAME}" ]] && command -v tmux >/dev/null 2>&1; then
  if tmux has-session -t "${SESSION_NAME}" 2>/dev/null; then
    tmux kill-session -t "${SESSION_NAME}"
    info "killed tmux session ${SESSION_NAME}"
  fi
fi

printf '\n[OK] branch-worktree-dev finish complete\n'
printf 'repo=%s\n' "${REPO}"
printf 'branch=%s\n' "${BRANCH}"
printf 'remote=%s\n' "${REMOTE_NAME}"
printf 'pushed=%s\n' "${DO_PUSH}"
printf 'api_stopped=%s\n' "${STOP_API}"
printf 'frontend_stopped=%s\n' "${STOP_FRONTEND}"
