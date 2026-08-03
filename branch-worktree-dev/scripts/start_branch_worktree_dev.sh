#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  start_branch_worktree_dev.sh [options]

Create a new Git branch/worktree, copy local runtime config when present, and
start the API plus frontend using repository-native commands.

Options:
  --repo PATH              Source Git repository. Defaults to current repo.
  --branch NAME            New branch name. Defaults to codex/YYYYMMDD-HHMMSS-dev.
  --base REF               Base ref for the new branch. Defaults to HEAD.
  --worktree PATH          Worktree path. Defaults to <repo>/.worktrees/<branch-slug>.
  --api-port PORT|auto     API port override. Defaults to auto.
  --fe-port PORT|auto      Frontend port override. Defaults to auto.
  --api-command COMMAND    API startup command, run from the new worktree.
  --frontend-command CMD   Frontend startup command, run from the new worktree.
  --session NAME           tmux session name. Defaults from branch slug.
  --startup-timeout SEC    Maximum readiness wait. Defaults to 60 seconds.
  --api-health-url URL     API readiness probe URL. Defaults to /api/v1/health on the API port.
  --frontend-health-url URL
                           Frontend readiness probe URL. Defaults to / on the frontend port.
  --no-wait                Do not wait for API/frontend readiness after starting commands.
  --allow-dirty            Allow creating from a dirty source worktree.
  --no-auto-commit         Do not create an automatic checkpoint commit when the source worktree is dirty.
  --commit-message MSG     Commit message for the automatic dirty-worktree checkpoint.
  --no-copy-runtime        Do not copy .branch-runtime.local or example runtime file.
  --no-start               Only create the branch/worktree and runtime file.
  --api-only               Start API only.
  --frontend-only          Start frontend only.
  -h, --help               Show this help.

Examples:
  start_branch_worktree_dev.sh --branch feature/chat-fix
  start_branch_worktree_dev.sh --branch feature/chat-fix --no-start
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

sanitize_slug() {
  printf '%s' "$1" \
    | tr '[:upper:]' '[:lower:]' \
    | sed -E 's#[^a-z0-9._-]+#-#g; s#^-+##; s#-+$##; s#-+#-#g'
}

is_port_free() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    if ss -ltn | awk '{print $4}' | grep -Eq "(^|:)${port}$"; then
      return 1
    fi
  fi
  if command -v lsof >/dev/null 2>&1; then
    if lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1; then
      return 1
    fi
  fi

  if (echo >/dev/tcp/127.0.0.1/"${port}") >/dev/null 2>&1; then
    return 1
  fi

  return 0
}

find_free_port() {
  local start="$1"
  local port
  for ((port = start; port < start + 400; port++)); do
    if is_port_free "${port}"; then
      printf '%s\n' "${port}"
      return 0
    fi
  done
  return 1
}

has_make_target() {
  local root="$1"
  local target="$2"
  [[ -f "${root}/Makefile" ]] || return 1
  grep -Eq "^${target}:" "${root}/Makefile"
}

quote_for_shell() {
  printf "%q" "$1"
}

run_background() {
  local label="$1"
  local command="$2"
  local cwd="$3"
  local log_file="$4"
  local pid_file="$5"

  : >"${log_file}"
  (
    cd "${cwd}"
    if command -v setsid >/dev/null 2>&1; then
      setsid bash -lc "${command}" >>"${log_file}" 2>&1 < /dev/null &
    else
      nohup bash -lc "${command}" >>"${log_file}" 2>&1 < /dev/null &
    fi
    printf '%s\n' "$!" >"${pid_file}"
  )
  info "started ${label}; pid=$(cat "${pid_file}") log=${log_file}"
}

http_ready() {
  local url="$1"
  local status

  command -v curl >/dev/null 2>&1 || return 1
  status="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 2 "${url}" 2>/dev/null || true)"
  [[ "${status}" =~ ^(2|3)[0-9][0-9]$ ]]
}

port_listening() {
  local port="$1"
  ! is_port_free "${port}"
}

wait_for_ready() {
  local label="$1"
  local url="$2"
  local port="$3"
  local timeout_seconds="$4"
  local log_file="$5"
  local start_ts now elapsed

  [[ "${WAIT_FOR_READY}" -eq 1 ]] || return 0

  info "waiting for ${label} readiness; max ${timeout_seconds}s"
  start_ts="$(date +%s)"
  while true; do
    if [[ -n "${url}" ]] && http_ready "${url}"; then
      info "${label} ready: ${url}"
      return 0
    fi

    if [[ -n "${url}" ]] && ! command -v curl >/dev/null 2>&1 && port_listening "${port}"; then
      info "${label} port is listening: ${port} (curl unavailable, skipped HTTP probe)"
      return 0
    fi

    if [[ -z "${url}" ]] && port_listening "${port}"; then
      info "${label} port is listening: ${port}"
      return 0
    fi

    now="$(date +%s)"
    elapsed=$((now - start_ts))
    if (( elapsed >= timeout_seconds )); then
      die "${label} did not become ready within ${timeout_seconds}s; log=${log_file}"
    fi
    sleep 1
  done
}

checkpoint_dirty_source() {
  local status_output commit_message commit_sha

  status_output="$(filtered_status_output)"
  [[ -n "${status_output}" ]] || return 0

  if [[ "${AUTO_COMMIT_DIRTY}" -ne 1 ]]; then
    printf '%s\n' "${status_output}" >&2
    die "source worktree is dirty; automatic checkpoint commit is disabled. Commit intentionally, rerun without --no-auto-commit, or explicitly pass --allow-dirty"
  fi

  commit_message="${AUTO_COMMIT_MESSAGE:-chore: checkpoint before branch-worktree-dev $(date +%Y-%m-%dT%H:%M:%S%z)}"
  info "source worktree is dirty; creating automatic checkpoint commit before opening a new worktree"
  git add -A
  git reset --quiet HEAD -- .codex .worktrees frontend/node_modules .branch-runtime.local .env 2>/dev/null || true
  if git diff --cached --quiet; then
    info "source worktree only has local runtime artifacts; skipping checkpoint commit"
    return 0
  fi
  git commit -m "${commit_message}"
  commit_sha="$(git rev-parse --short HEAD)"
  info "created automatic checkpoint commit ${commit_sha}"
}

REPO=""
BRANCH=""
BASE_REF="HEAD"
WORKTREE=""
API_PORT_VALUE="auto"
FE_PORT_VALUE="auto"
API_COMMAND=""
FRONTEND_COMMAND=""
SESSION_NAME=""
STARTUP_TIMEOUT="${BRANCH_WORKTREE_DEV_STARTUP_TIMEOUT:-60}"
API_HEALTH_URL=""
FRONTEND_HEALTH_URL=""
WAIT_FOR_READY=1
ALLOW_DIRTY=0
AUTO_COMMIT_DIRTY=1
AUTO_COMMIT_MESSAGE=""
COPY_RUNTIME=1
START_RUNTIME=1
START_API=1
START_FRONTEND=1

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
    --base)
      BASE_REF="${2:-}"
      shift 2
      ;;
    --worktree)
      WORKTREE="${2:-}"
      shift 2
      ;;
    --api-port)
      API_PORT_VALUE="${2:-}"
      shift 2
      ;;
    --fe-port|--frontend-port)
      FE_PORT_VALUE="${2:-}"
      shift 2
      ;;
    --api-command)
      API_COMMAND="${2:-}"
      shift 2
      ;;
    --frontend-command)
      FRONTEND_COMMAND="${2:-}"
      shift 2
      ;;
    --session)
      SESSION_NAME="${2:-}"
      shift 2
      ;;
    --startup-timeout)
      STARTUP_TIMEOUT="${2:-}"
      shift 2
      ;;
    --api-health-url)
      API_HEALTH_URL="${2:-}"
      shift 2
      ;;
    --frontend-health-url)
      FRONTEND_HEALTH_URL="${2:-}"
      shift 2
      ;;
    --no-wait)
      WAIT_FOR_READY=0
      shift
      ;;
    --allow-dirty)
      ALLOW_DIRTY=1
      shift
      ;;
    --no-auto-commit)
      AUTO_COMMIT_DIRTY=0
      shift
      ;;
    --commit-message)
      AUTO_COMMIT_MESSAGE="${2:-}"
      shift 2
      ;;
    --no-copy-runtime)
      COPY_RUNTIME=0
      shift
      ;;
    --no-start)
      START_RUNTIME=0
      shift
      ;;
    --api-only)
      START_FRONTEND=0
      shift
      ;;
    --frontend-only)
      START_API=0
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
SOURCE_WORKTREE="${REPO}"
SOURCE_BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || printf 'HEAD')"

if [[ -z "${BRANCH}" ]]; then
  BRANCH="codex/$(date +%Y%m%d-%H%M%S)-dev"
fi

BRANCH_SLUG="$(sanitize_slug "${BRANCH}")"
[[ -n "${BRANCH_SLUG}" ]] || die "branch name produced an empty slug"

if [[ -z "${WORKTREE}" ]]; then
  WORKTREE="${REPO}/.worktrees/${BRANCH_SLUG}"
fi

if [[ -z "${SESSION_NAME}" ]]; then
  SESSION_NAME="dev-${BRANCH_SLUG}"
fi
SESSION_NAME="$(sanitize_slug "${SESSION_NAME}")"

if [[ "${START_API}" -eq 0 && "${START_FRONTEND}" -eq 0 ]]; then
  die "--api-only and --frontend-only cannot both disable all startup"
fi

if [[ "${ALLOW_DIRTY}" -ne 1 ]]; then
  checkpoint_dirty_source
fi

if git show-ref --verify --quiet "refs/heads/${BRANCH}"; then
  die "branch already exists: ${BRANCH}"
fi

if [[ -e "${WORKTREE}" ]]; then
  die "worktree path already exists: ${WORKTREE}"
fi

mkdir -p "$(dirname "${WORKTREE}")"
info "creating worktree ${WORKTREE} on branch ${BRANCH} from ${BASE_REF}"
git worktree add -b "${BRANCH}" "${WORKTREE}" "${BASE_REF}"

if [[ "${API_PORT_VALUE}" == "auto" ]]; then
  API_PORT_VALUE="$(find_free_port 18020)" || die "could not find a free API port"
  if [[ "${API_PORT_VALUE}" != "18020" ]]; then
    info "default API port 18020 is busy; using ${API_PORT_VALUE} instead"
  fi
fi
if [[ "${FE_PORT_VALUE}" == "auto" ]]; then
  FE_PORT_VALUE="$(find_free_port 3100)" || die "could not find a free frontend port"
  if [[ "${FE_PORT_VALUE}" != "3100" ]]; then
    info "default frontend port 3100 is busy; using ${FE_PORT_VALUE} instead"
  fi
fi

case "${API_PORT_VALUE}" in
  ''|*[!0-9]*) die "API port must be numeric or auto" ;;
esac
case "${FE_PORT_VALUE}" in
  ''|*[!0-9]*) die "frontend port must be numeric or auto" ;;
esac
case "${STARTUP_TIMEOUT}" in
  ''|*[!0-9]*) die "startup timeout must be numeric seconds" ;;
esac

if ! is_port_free "${API_PORT_VALUE}"; then
  die "requested API port ${API_PORT_VALUE} is already in use; pick another port or use --api-port auto"
fi
if ! is_port_free "${FE_PORT_VALUE}"; then
  die "requested frontend port ${FE_PORT_VALUE} is already in use; pick another port or use --fe-port auto"
fi

if [[ -z "${API_HEALTH_URL}" ]]; then
  API_HEALTH_URL="http://127.0.0.1:${API_PORT_VALUE}/api/v1/health"
fi
if [[ -z "${FRONTEND_HEALTH_URL}" ]]; then
  FRONTEND_HEALTH_URL="http://127.0.0.1:${FE_PORT_VALUE}/"
fi

COMPOSE_SLUG="$(sanitize_slug "$(basename "${REPO}")-${BRANCH_SLUG}")"
COMPOSE_SLUG="${COMPOSE_SLUG:0:54}"
COMPOSE_SLUG="${COMPOSE_SLUG%-}"
[[ -n "${COMPOSE_SLUG}" ]] || COMPOSE_SLUG="branch-worktree-dev"

RUNTIME_TARGET="${WORKTREE}/.branch-runtime.local"
if [[ "${COPY_RUNTIME}" -eq 1 ]]; then
  if [[ -f "${REPO}/.branch-runtime.local" ]]; then
    cp "${REPO}/.branch-runtime.local" "${RUNTIME_TARGET}"
    info "copied local runtime config to new worktree without printing it"
  elif [[ -f "${WORKTREE}/.branch-runtime.local.example" ]]; then
    cp "${WORKTREE}/.branch-runtime.local.example" "${RUNTIME_TARGET}"
    info "created .branch-runtime.local from example"
  fi

  if [[ -f "${REPO}/.env" ]]; then
    cp "${REPO}/.env" "${WORKTREE}/.env"
    info "copied local .env to new worktree without printing it"
  fi

  if [[ -d "${REPO}/frontend/node_modules" && ! -e "${WORKTREE}/frontend/node_modules" ]]; then
    ln -s "${REPO}/frontend/node_modules" "${WORKTREE}/frontend/node_modules"
    info "linked source frontend/node_modules into new worktree"
  fi

  if [[ -f "${RUNTIME_TARGET}" ]]; then
    {
      printf '\n# Generated by branch-worktree-dev on %s.\n' "$(date -Iseconds)"
      printf '# Local ignored runtime overrides for this worktree only.\n'
      printf 'BRANCH_NAME=%s\n' "${BRANCH}"
      printf 'API_PORT=%s\n' "${API_PORT_VALUE}"
      printf 'LOCAL_API_PORT=%s\n' "${API_PORT_VALUE}"
      printf 'FE_PORT=%s\n' "${FE_PORT_VALUE}"
      printf 'BUGFIX_FE_PORT=%s\n' "${FE_PORT_VALUE}"
      printf 'VITE_API_TARGET=http://127.0.0.1:%s\n' "${API_PORT_VALUE}"
      printf 'COMPOSE_PROJECT_NAME=%s\n' "${COMPOSE_SLUG}"
      printf 'API_CONTAINER_NAME=%s-api\n' "${COMPOSE_SLUG}"
      printf 'BUGFIX_API_CONTAINER_NAME=%s-api\n' "${COMPOSE_SLUG}"
    } >>"${RUNTIME_TARGET}"
    info "appended isolated local runtime overrides to ${RUNTIME_TARGET}"
  else
    info "no .branch-runtime.local found or created; startup commands may need explicit env"
  fi
fi

if [[ -z "${API_COMMAND}" && "${START_RUNTIME}" -eq 1 && "${START_API}" -eq 1 ]]; then
  if has_make_target "${WORKTREE}" "dev-local-api"; then
    API_COMMAND="make dev-local-api"
  else
    die "no API command discovered; pass --api-command or use --no-start"
  fi
fi

FRONTEND_ENV_PREFIX=""
if [[ -f "${WORKTREE}/frontend/vite.config.ts" || -f "${WORKTREE}/frontend/vite.config.js" ]]; then
  FRONTEND_ENV_PREFIX="CHOKIDAR_USEPOLLING=${CHOKIDAR_USEPOLLING:-true} "
fi

if [[ -z "${FRONTEND_COMMAND}" && "${START_RUNTIME}" -eq 1 && "${START_FRONTEND}" -eq 1 ]]; then
  if has_make_target "${WORKTREE}" "dev-local-frontend"; then
    FRONTEND_COMMAND="${FRONTEND_ENV_PREFIX}make dev-local-frontend"
  elif [[ -f "${WORKTREE}/frontend/package.json" ]]; then
    FRONTEND_COMMAND="${FRONTEND_ENV_PREFIX}cd frontend && VITE_API_TARGET=http://127.0.0.1:${API_PORT_VALUE} npm run dev -- --host 0.0.0.0 --port ${FE_PORT_VALUE} --strictPort"
  else
    die "no frontend command discovered; pass --frontend-command or use --api-only/--no-start"
  fi
fi

LOG_DIR="${WORKTREE}/.codex/dev-runtime"
mkdir -p "${LOG_DIR}"
METADATA_FILE="${LOG_DIR}/runtime.env"
HANDOFF_FILE="${LOG_DIR}/worktree-handoff.md"
ENTER_WORKTREE_SCRIPT="${LOG_DIR}/enter-worktree.sh"

{
  printf 'SOURCE_WORKTREE=%q\n' "${SOURCE_WORKTREE}"
  printf 'SOURCE_BRANCH=%q\n' "${SOURCE_BRANCH}"
  printf 'BRANCH=%q\n' "${BRANCH}"
  printf 'WORKTREE=%q\n' "${WORKTREE}"
  printf 'LOG_DIR=%q\n' "${LOG_DIR}"
  printf 'API_PORT=%q\n' "${API_PORT_VALUE}"
  printf 'FE_PORT=%q\n' "${FE_PORT_VALUE}"
  printf 'SESSION_NAME=%q\n' "${SESSION_NAME}"
  printf 'START_RUNTIME=%q\n' "${START_RUNTIME}"
  printf 'START_API=%q\n' "${START_API}"
  printf 'START_FRONTEND=%q\n' "${START_FRONTEND}"
  printf 'API_COMMAND=%q\n' "${API_COMMAND}"
  printf 'FRONTEND_COMMAND=%q\n' "${FRONTEND_COMMAND}"
  printf 'STARTUP_TIMEOUT=%q\n' "${STARTUP_TIMEOUT}"
  printf 'WAIT_FOR_READY=%q\n' "${WAIT_FOR_READY}"
  printf 'API_HEALTH_URL=%q\n' "${API_HEALTH_URL}"
  printf 'FRONTEND_HEALTH_URL=%q\n' "${FRONTEND_HEALTH_URL}"
  printf 'API_PID_FILE=%q\n' "${LOG_DIR}/api.pid"
  printf 'FRONTEND_PID_FILE=%q\n' "${LOG_DIR}/frontend.pid"
  printf 'RUNTIME_CONFIG=%q\n' "${RUNTIME_TARGET}"
  printf 'COMPOSE_PROJECT_NAME=%q\n' "${COMPOSE_SLUG}"
  printf 'HANDOFF_FILE=%q\n' "${HANDOFF_FILE}"
  printf 'ENTER_WORKTREE_SCRIPT=%q\n' "${ENTER_WORKTREE_SCRIPT}"
} >"${METADATA_FILE}"
info "wrote runtime metadata to ${METADATA_FILE}"

cat >"${HANDOFF_FILE}" <<EOF
# branch-worktree-dev handoff

- source_worktree: ${SOURCE_WORKTREE}
- source_branch: ${SOURCE_BRANCH}
- branch: ${BRANCH}
- worktree: ${WORKTREE}
- api_url: http://127.0.0.1:${API_PORT_VALUE}
- frontend_url: http://127.0.0.1:${FE_PORT_VALUE}
- logs: ${LOG_DIR}

All follow-up edits, tests, and browser checks must run from:

\`\`\`bash
cd ${WORKTREE@Q}
\`\`\`

If the current agent or window cannot relocate into that path, stop after setup
and resume the task in a new window or session rooted at the worktree above.
Editing the source worktree after this handoff is non-compliant skill usage.
EOF
info "wrote handoff file to ${HANDOFF_FILE}"

cat >"${ENTER_WORKTREE_SCRIPT}" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd ${WORKTREE@Q}
exec "\${SHELL:-bash}" -l
EOF
chmod +x "${ENTER_WORKTREE_SCRIPT}"
info "wrote enter-worktree helper to ${ENTER_WORKTREE_SCRIPT}"

if [[ "${START_RUNTIME}" -eq 1 ]]; then
  if command -v tmux >/dev/null 2>&1; then
    if tmux has-session -t "${SESSION_NAME}" 2>/dev/null; then
      die "tmux session already exists: ${SESSION_NAME}"
    fi

    if [[ "${START_API}" -eq 1 ]]; then
      tmux new-session -d -s "${SESSION_NAME}" -n api -c "${WORKTREE}" \
        "bash -lc $(quote_for_shell "${API_COMMAND} 2>&1 | tee $(quote_for_shell "${LOG_DIR}/api.log")")"
      info "started API in tmux session ${SESSION_NAME}:api"
      wait_for_ready "API" "${API_HEALTH_URL}" "${API_PORT_VALUE}" "${STARTUP_TIMEOUT}" "${LOG_DIR}/api.log"
    else
      tmux new-session -d -s "${SESSION_NAME}" -n shell -c "${WORKTREE}" "bash"
    fi

    if [[ "${START_FRONTEND}" -eq 1 ]]; then
      tmux new-window -t "${SESSION_NAME}:" -n frontend -c "${WORKTREE}" \
        "bash -lc $(quote_for_shell "${FRONTEND_COMMAND} 2>&1 | tee $(quote_for_shell "${LOG_DIR}/frontend.log")")"
      info "started frontend in tmux session ${SESSION_NAME}:frontend"
      wait_for_ready "frontend" "${FRONTEND_HEALTH_URL}" "${FE_PORT_VALUE}" "${STARTUP_TIMEOUT}" "${LOG_DIR}/frontend.log"
    fi
  else
    if [[ "${START_API}" -eq 1 ]]; then
      run_background "API" "${API_COMMAND}" "${WORKTREE}" "${LOG_DIR}/api.log" "${LOG_DIR}/api.pid"
      wait_for_ready "API" "${API_HEALTH_URL}" "${API_PORT_VALUE}" "${STARTUP_TIMEOUT}" "${LOG_DIR}/api.log"
    fi
    if [[ "${START_FRONTEND}" -eq 1 ]]; then
      run_background "frontend" "${FRONTEND_COMMAND}" "${WORKTREE}" "${LOG_DIR}/frontend.log" "${LOG_DIR}/frontend.pid"
      wait_for_ready "frontend" "${FRONTEND_HEALTH_URL}" "${FE_PORT_VALUE}" "${STARTUP_TIMEOUT}" "${LOG_DIR}/frontend.log"
    fi
  fi
else
  info "created branch/worktree only; runtime startup skipped"
fi

printf '\n[OK] branch-worktree-dev complete\n'
printf 'source_worktree=%s\n' "${SOURCE_WORKTREE}"
printf 'source_branch=%s\n' "${SOURCE_BRANCH}"
printf 'branch=%s\n' "${BRANCH}"
printf 'worktree=%s\n' "${WORKTREE}"
printf 'api_url=http://127.0.0.1:%s\n' "${API_PORT_VALUE}"
printf 'frontend_url=http://127.0.0.1:%s\n' "${FE_PORT_VALUE}"
printf 'logs=%s\n' "${LOG_DIR}"
printf 'api_health_url=%s\n' "${API_HEALTH_URL}"
printf 'frontend_health_url=%s\n' "${FRONTEND_HEALTH_URL}"
printf 'readiness_wait=%s\n' "${WAIT_FOR_READY}"
printf 'handoff_file=%s\n' "${HANDOFF_FILE}"
printf 'cd_command=cd %q\n' "${WORKTREE}"
printf 'enter_worktree_command=bash %q\n' "${ENTER_WORKTREE_SCRIPT}"
printf 'continue_in_worktree_only=true\n'
if [[ "${START_RUNTIME}" -eq 1 && "$(command -v tmux || true)" != "" ]]; then
  printf 'tmux_session=%s\n' "${SESSION_NAME}"
  printf 'attach_command=tmux attach -t %s\n' "${SESSION_NAME}"
fi
