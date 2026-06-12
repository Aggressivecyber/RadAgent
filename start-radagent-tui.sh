#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

ACTION="run"
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
    --help|-h)
      cat <<'EOF'
Usage: ./start-radagent-tui.sh [--setup|--check] [radagent-tui options]

One-click launcher for the RadAgent Textual TUI.

Launcher options:
  --setup    Create .venv and install TUI dependencies, then exit
  --check    Verify the TUI can import in .venv, then exit
  --help     Show this help

TUI options are passed through, for example:
  ./start-radagent-tui.sh --mode test
  ./start-radagent-tui.sh --theme neon-lab
EOF
      exit 0
      ;;
    *)
      break
      ;;
  esac
done

if [ ! -f ".venv/bin/activate" ]; then
  echo "Creating .venv ..."
  python3 -m venv .venv
fi

export RADAGENT_KEEP_AUTO_VENV=1
source ".venv/bin/activate"

check_tui_imports() {
  python - <<'PY' >/dev/null 2>&1
import textual
from agent_core.tui.app import create_app_class

create_app_class()
PY
}

if ! check_tui_imports; then
  echo "Installing RadAgent TUI dependencies ..."
  python -m pip install -e '.[tui]'
fi

if [[ "$ACTION" == "setup" ]]; then
  echo "RadAgent TUI dependencies are installed."
  exit 0
fi

if [[ "$ACTION" == "check" ]]; then
  check_tui_imports
  python - <<'PY'
import textual

print(f"RadAgent TUI import OK (Textual {textual.__version__})")
PY
  exit 0
fi

exec python -m agent_core.tui "$@"
