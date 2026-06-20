#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$ROOT/.venv"
PYTHON_BIN="python3"
EXTRAS="dev"
SKIP_INSTALL=0
CHECK_ONLY=0

usage() {
  cat <<'EOF'
RadAgent environment setup

Usage:
  ./scripts/setup_radagent_env.sh [options]

Options:
  --venv PATH       Virtual environment path (default: .venv)
  --python COMMAND  Python interpreter used to create the venv (default: python3)
  --extras EXTRAS   Editable install extras, for example dev,tui (default: dev)
  --skip-install    Create/check the venv without installing Python packages
  --check-only      Check the current environment and external tools, then exit
  --help, -h        Show this help

Examples:
  ./scripts/setup_radagent_env.sh
  ./scripts/setup_radagent_env.sh --extras dev,tui
  ./scripts/setup_radagent_env.sh --venv /tmp/radagent-venv --check-only
EOF
}

info() { printf '  [info] %s\n' "$*"; }
ok() { printf '  [ok] %s\n' "$*"; }
warn() { printf '  [warn] %s\n' "$*"; }
fail() { printf '  [error] %s\n' "$*" >&2; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --venv)
      VENV_DIR="${2:?--venv requires a path}"
      shift 2
      ;;
    --python)
      PYTHON_BIN="${2:?--python requires a command}"
      shift 2
      ;;
    --extras)
      EXTRAS="${2:?--extras requires a value}"
      shift 2
      ;;
    --skip-install)
      SKIP_INSTALL=1
      shift
      ;;
    --check-only)
      CHECK_ONLY=1
      SKIP_INSTALL=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      fail "Unknown option: $1"
      usage >&2
      exit 2
      ;;
  esac
done

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    fail "$1 was not found on PATH."
    exit 1
  fi
}

check_python_version() {
  "$PYTHON_BIN" - <<'PY'
import sys

major, minor = sys.version_info[:2]
if (major, minor) < (3, 11):
    raise SystemExit(f"Python {major}.{minor} found, but RadAgent requires Python 3.11+")
print(f"Python {major}.{minor}")
PY
}

venv_python() {
  printf '%s/bin/python' "$VENV_DIR"
}

detect_geant4() {
  if ! command -v cmake >/dev/null 2>&1; then
    warn "cmake not found; Geant4 benchmark builds cannot run."
    return 0
  fi
  ok "cmake: $(cmake --version | sed -n '1s/cmake version //p')"

  local detect_dir
  detect_dir="$(mktemp -d "${TMPDIR:-/tmp}/radagent-geant4-detect.XXXXXX")"
  if cmake -S "$ROOT/benchmarks/geant4_photon_attenuation" -B "$detect_dir" >/dev/null 2>&1; then
    ok "Geant4 CMake package detected."
  else
    warn "Geant4 CMake package not detected."
    warn "For full NIST simulation, source geant4.sh or set GEANT4_INSTALL/Geant4_DIR/CMAKE_PREFIX_PATH."
  fi
  rm -rf "$detect_dir"
}

main() {
  cd "$ROOT"
  require_command "$PYTHON_BIN"
  info "Repository: $ROOT"
  info "Virtual environment: $VENV_DIR"
  check_python_version

  if [[ ! -f "$VENV_DIR/bin/activate" && "$CHECK_ONLY" -eq 0 ]]; then
    info "Creating virtual environment ..."
    "$PYTHON_BIN" -m venv "$VENV_DIR"
  fi

  if [[ -f "$VENV_DIR/bin/activate" ]]; then
    # shellcheck disable=SC1090
    source "$VENV_DIR/bin/activate"
    ok "venv active: $VENV_DIR"
  elif [[ "$CHECK_ONLY" -eq 1 ]]; then
    warn "venv not found: $VENV_DIR"
  else
    fail "venv could not be created: $VENV_DIR"
    exit 1
  fi

  if [[ "$SKIP_INSTALL" -eq 0 ]]; then
    info "Upgrading packaging tools ..."
    "$(venv_python)" -m pip install --upgrade pip setuptools wheel

    if [[ -n "$EXTRAS" ]]; then
      info "Installing RadAgent editable package with extras: $EXTRAS"
      "$(venv_python)" -m pip install -e "$ROOT[$EXTRAS]"
    else
      info "Installing RadAgent editable package without extras"
      "$(venv_python)" -m pip install -e "$ROOT"
    fi
  else
    info "Skipping Python package installation."
  fi

  if [[ -x "$(venv_python)" ]]; then
    if "$(venv_python)" - <<'PY' >/dev/null 2>&1
import agent_core
import langgraph
import pydantic
PY
    then
      ok "Core Python imports are available."
    else
      warn "Core imports are not available yet. Run without --skip-install to install dependencies."
    fi
  fi

  detect_geant4
  ok "Environment setup/check finished."
}

main "$@"
