#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
WEB_DIR="$ROOT/web_workbench"
VENV_DIR="$ROOT/.venv"

ACTION="run"
HOST="127.0.0.1"
BACKEND_PORT="8787"
FRONTEND_PORT="5174"
ENV_PATH=""
INSTALL_DEPS=1

usage() {
  cat <<'EOF'
Usage: ./start-radagent-web.sh [options]

One-click launcher for the RadAgent web workbench.

Options:
  --setup                  Create .venv, install backend/frontend dependencies, then exit
  --check                  Verify backend/frontend imports without starting servers
  --host HOST              Host for both servers (default: 127.0.0.1)
  --backend-port PORT      Backend API port (default: 8787)
  --frontend-port PORT     Vite frontend port (default: 5174)
  --env-path PATH          Env file used by editable model settings
  --no-install             Do not install missing dependencies automatically
  --help, -h               Show this help

Examples:
  ./start-radagent-web.sh
  ./start-radagent-web.sh --backend-port 8888 --frontend-port 5175
  ./start-radagent-web.sh --setup
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --setup)
      ACTION="setup"
      shift
      ;;
    --check)
      ACTION="check"
      shift
      ;;
    --host)
      HOST="${2:?--host requires a value}"
      shift 2
      ;;
    --backend-port)
      BACKEND_PORT="${2:?--backend-port requires a value}"
      shift 2
      ;;
    --frontend-port)
      FRONTEND_PORT="${2:?--frontend-port requires a value}"
      shift 2
      ;;
    --env-path)
      ENV_PATH="${2:?--env-path requires a value}"
      shift 2
      ;;
    --no-install)
      INSTALL_DEPS=0
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

info() { printf '  \033[0;36m▸\033[0m %s\n' "$*"; }
ok() { printf '  \033[0;32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[1;33m⚠\033[0m %s\n' "$*"; }
fail() { printf '  \033[0;31m✗\033[0m %s\n' "$*" >&2; }

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    fail "$1 was not found."
    exit 1
  fi
}

ensure_python_env() {
  require_command python3
  if [[ ! -f "$VENV_DIR/bin/activate" ]]; then
    info "Creating .venv ..."
    python3 -m venv "$VENV_DIR"
  fi

  # shellcheck disable=SC1091
  source "$VENV_DIR/bin/activate"

  if ! python - <<'PY' >/dev/null 2>&1
from agent_core.web.server import build_server
PY
  then
    if [[ "$INSTALL_DEPS" -ne 1 ]]; then
      fail "Backend dependencies are missing. Re-run without --no-install or install with: python -m pip install -e ."
      exit 1
    fi
    info "Installing backend dependencies ..."
    python -m pip install -e "$ROOT"
  fi
  ok "Backend import OK"
}

ensure_frontend_env() {
  require_command npm
  if [[ ! -d "$WEB_DIR/node_modules" ]]; then
    if [[ "$INSTALL_DEPS" -ne 1 ]]; then
      fail "Frontend dependencies are missing. Re-run without --no-install or run: cd web_workbench && npm install"
      exit 1
    fi
    info "Installing frontend dependencies ..."
    if [[ -f "$WEB_DIR/package-lock.json" ]]; then
      npm --prefix "$WEB_DIR" ci
    else
      npm --prefix "$WEB_DIR" install
    fi
  fi

  if [[ ! -x "$WEB_DIR/node_modules/.bin/vite" ]]; then
    fail "Vite is not installed under web_workbench/node_modules."
    exit 1
  fi
  ok "Frontend dependencies OK"
}

wait_for_http() {
  local name="$1"
  local url="$2"
  local attempts=60
  for _ in $(seq 1 "$attempts"); do
    if python - "$url" <<'PY' >/dev/null 2>&1
import sys
from urllib.request import urlopen

with urlopen(sys.argv[1], timeout=1) as response:
    raise SystemExit(0 if 200 <= response.status < 500 else 1)
PY
    then
      ok "$name ready: $url"
      return 0
    fi
    sleep 0.5
  done
  warn "$name did not answer yet: $url"
}

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  trap - EXIT INT TERM
  if [[ -n "$FRONTEND_PID" ]] && kill -0 "$FRONTEND_PID" >/dev/null 2>&1; then
    kill "$FRONTEND_PID" >/dev/null 2>&1 || true
  fi
  if [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
    kill "$BACKEND_PID" >/dev/null 2>&1 || true
  fi
  wait "$FRONTEND_PID" "$BACKEND_PID" >/dev/null 2>&1 || true
}

ensure_python_env
ensure_frontend_env

if [[ "$ACTION" == "setup" ]]; then
  ok "RadAgent web dependencies are installed."
  exit 0
fi

if [[ "$ACTION" == "check" ]]; then
  python - <<'PY'
from agent_core.web.server import build_server

print("Backend check OK")
PY
  "$WEB_DIR/node_modules/.bin/vite" --version
  ok "RadAgent web launcher check passed."
  exit 0
fi

trap cleanup EXIT INT TERM

BACKEND_ARGS=(--host "$HOST" --port "$BACKEND_PORT")
if [[ -n "$ENV_PATH" ]]; then
  BACKEND_ARGS+=(--env-path "$ENV_PATH")
fi

info "Starting backend API on http://$HOST:$BACKEND_PORT"
python -m agent_core.web.server "${BACKEND_ARGS[@]}" &
BACKEND_PID=$!

info "Starting frontend on http://$HOST:$FRONTEND_PORT"
(
  cd "$WEB_DIR"
  BROWSER=none npm run dev -- --host "$HOST" --port "$FRONTEND_PORT" --strictPort
) &
FRONTEND_PID=$!

wait_for_http "Backend API" "http://$HOST:$BACKEND_PORT/api/status"
wait_for_http "Frontend" "http://$HOST:$FRONTEND_PORT"

cat <<EOF

RadAgent web workbench is running.
  Frontend: http://$HOST:$FRONTEND_PORT
  Backend:  http://$HOST:$BACKEND_PORT

Press Ctrl+C to stop both servers.
EOF

while true; do
  if ! kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
    wait "$BACKEND_PID"
    exit $?
  fi
  if ! kill -0 "$FRONTEND_PID" >/dev/null 2>&1; then
    wait "$FRONTEND_PID"
    exit $?
  fi
  sleep 1
done
