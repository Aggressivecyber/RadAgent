#!/usr/bin/env bash
# RadAgent Interactive REPL — one-click launcher
#
# Usage:
#   ./repl.sh                        # 默认 dev 模式
#   ./repl.sh --mode mvp1_acceptance # 指定模式
#   ./repl.sh --help                 # 查看所有选项

set -euo pipefail
cd "$(dirname "$0")"

# 加载 .env（如果存在）
if [ -f .env ]; then
    set -a; source .env; set +a
fi

# 加载 Geant4 环境（静默失败）
if [ -f /etc/profile.d/geant4.sh ]; then
    source /etc/profile.d/geant4.sh 2>/dev/null || true
fi

# 激活 venv
if [ -d .venv ]; then
    source .venv/bin/activate
fi

# 启动 REPL
exec python -m agent_core.main -i "$@"
