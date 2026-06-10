#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [ ! -f ".venv/bin/activate" ]; then
  echo "Creating .venv ..."
  python3 -m venv .venv
fi

export RADAGENT_KEEP_AUTO_VENV=1
source ".venv/bin/activate"

if ! python -c "import textual" >/dev/null 2>&1; then
  echo "Installing RadAgent TUI dependencies ..."
  python -m pip install -e '.[tui]'
fi

exec python -m agent_core.tui "$@"
