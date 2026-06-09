#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# RadAgent Interactive REPL — one-click launcher
#
# Usage:
#   ./repl.sh                         # 默认 acceptance 模式
#   ./repl.sh --dev                   # 开发模式（不要求 Geant4 环境）
#   ./repl.sh --mode mvp1_acceptance  # 显式指定模式
#   ./repl.sh --setup                 # 仅安装依赖，不启动 REPL
#   ./repl.sh --check                 # 检查环境状态
#   ./repl.sh --help                  # 查看帮助
# ─────────────────────────────────────────────────────────────────────

set -euo pipefail
cd "$(dirname "$0")"

# ── 颜色定义 ────────────────────────────────────────────────────────

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
DIM='\033[2m'
BOLD='\033[1m'
NC='\033[0m'  # No Color

# ── 辅助函数 ────────────────────────────────────────────────────────

info()    { echo -e "  ${CYAN}▸${NC} $*"; }
ok()      { echo -e "  ${GREEN}✓${NC} $*"; }
warn()    { echo -e "  ${YELLOW}⚠${NC} $*"; }
fail()    { echo -e "  ${RED}✗${NC} $*"; }
section() { echo -e "\n${BOLD}$*${NC}"; }

# ── Banner ──────────────────────────────────────────────────────────

banner() {
    echo -e "${CYAN}"
    cat << 'EOF'
    ____                _           ___    ____
   / __ \____ _____ _  (_)_______  /   |  /  _/
  / /_/ / __ `/ __ `/ / / ___/ _ \/ /| |  / /
 / _, _/ /_/ / /_/ / / / /__/  __/ ___ |_/ /
/_/ |_|\__,_/\__,_/_/_/\___/\___/_/  |_/___/
EOF
    echo -e "${NC}"
    echo -e "  ${DIM}Radiation Simulation Agent — Geant4 · TCAD · ngspice${NC}"
    echo ""
}

# ── 参数解析 ────────────────────────────────────────────────────────

MODE="acceptance"
ACTION="run"  # run | setup | check

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dev)
            MODE="test"
            shift
            ;;
        --mode)
            MODE="$2"
            shift 2
            ;;
        --setup)
            ACTION="setup"
            shift
            ;;
        --check)
            ACTION="check"
            shift
            ;;
        --help|-h)
            banner
            echo -e "${BOLD}Usage:${NC}"
            echo "  ./repl.sh                         # 默认 acceptance 模式"
            echo "  ./repl.sh --dev                   # 开发模式"
            echo "  ./repl.sh --mode acceptance       # 显式指定模式 (strict|test|acceptance|production)"
            echo "  ./repl.sh --setup                 # 安装依赖"
            echo "  ./repl.sh --check                 # 检查环境"
            echo ""
            exit 0
            ;;
        *)
            # 透传给 python
            break
            ;;
    esac
done

# ── 环境检查 ────────────────────────────────────────────────────────

check_python() {
    section "Python"
    if ! command -v python3 &>/dev/null; then
        fail "python3 未找到，请安装 Python 3.11+"
        exit 1
    fi

    PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    PY_MAJOR=$(python3 -c "import sys; print(sys.version_info.major)")
    PY_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)")

    if [[ "$PY_MAJOR" -lt 3 ]] || [[ "$PY_MAJOR" -eq 3 && "$PY_MINOR" -lt 11 ]]; then
        fail "Python $PY_VERSION — 需要 3.11+"
        exit 1
    fi
    ok "Python $PY_VERSION"
}

check_venv() {
    section "Virtual Environment"
    if [[ ! -d .venv ]]; then
        info "创建 .venv ..."
        python3 -m venv .venv
        ok ".venv 已创建"
    else
        ok ".venv 已存在"
    fi

    # shellcheck disable=SC1091
    source .venv/bin/activate >/dev/null 2>&1
    ok "已激活 (.venv)"
}

install_deps() {
    section "Dependencies"
    if ! python3 -c "import langgraph" &>/dev/null; then
        info "安装依赖 ..."
        pip install -e ".[dev]" -q 2>&1 | tail -3
        ok "依赖已安装"
    else
        ok "依赖已就绪"
    fi
}

check_api_key() {
    section "API Key"
    # 先加载 .env
    if [[ -f .env ]]; then
        set -a; source .env >/dev/null 2>&1; set +a
    fi

    local key_env="${RADAGENT_LITE_API_KEY_ENV:-RADAGENT_API_KEY}"
    local key_val="${!key_env:-}"

    if [[ -z "$key_val" ]] || [[ "$key_val" == "your_api_key_here" ]]; then
        warn "API key 未配置 (env: $key_env)"
        warn "请在 .env 中设置 RADAGENT_API_KEY 或导出 DEEPSEEK_API_KEY"
    else
        ok "API key 已配置 (${key_val:0:10}...)"
    fi
}

check_ollama() {
    section "Ollama (RAG)"
    if curl -s --connect-timeout 2 http://localhost:11434/api/tags &>/dev/null; then
        ok "Ollama 运行中"
        # 检查 bge-m3 模型
        if curl -s http://localhost:11434/api/tags | grep -q "bge-m3" 2>/dev/null; then
            ok "bge-m3 嵌入模型已就绪"
        else
            warn "bge-m3 模型未找到，RAG 检索可能不可用"
        fi
    else
        warn "Ollama 未运行 — RAG 检索将不可用"
        warn "启动: systemctl start ollama 或 ollama serve"
    fi
}

check_geant4() {
    if [[ "$MODE" == "test" ]]; then
        return
    fi

    section "Geant4"
    if [[ -f /etc/profile.d/geant4.sh ]]; then
        source /etc/profile.d/geant4.sh 2>/dev/null || true
        ok "Geant4 环境已加载"
    else
        warn "Geant4 环境文件未找到 (/etc/profile.d/geant4.sh)"
    fi
}

check_workspace() {
    section "Workspace"
    local ws="${RADAGENT_WORKSPACE_ROOT:-./simulation_workspace}"
    if [[ -d "$ws" ]]; then
        local job_count
        job_count=$(find "$ws/jobs" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l)
        ok "工作区: $ws ($job_count jobs)"
    else
        info "工作区将自动创建: $ws"
    fi
}

# ── 主流程 ──────────────────────────────────────────────────────────

main() {
    banner

    check_python
    check_venv
    install_deps
    check_api_key
    check_ollama
    check_geant4
    check_workspace

    if [[ "$ACTION" == "check" ]]; then
        echo ""
        echo -e "${GREEN}环境检查完成。${NC}"
        exit 0
    fi

    if [[ "$ACTION" == "setup" ]]; then
        echo ""
        echo -e "${GREEN}依赖安装完成。${NC}"
        exit 0
    fi

    # 启动 REPL
    echo ""
    echo -e "${DIM}────────────────────────────────────────────────${NC}"
    echo -e "  模式: ${BOLD}$MODE${NC}"
    echo -e "  输入自然语言或 ${BOLD}/help${NC} 查看命令"
    echo -e "${DIM}────────────────────────────────────────────────${NC}"
    echo ""

    exec python -m agent_core.main -i --mode "$MODE" "$@"
}

main
