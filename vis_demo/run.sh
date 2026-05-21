#!/bin/bash
# RadAgent 3D Visualization Demo Launcher
# 绕过 VSCode snap 终端的 glibc 冲突
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="${SCRIPT_DIR}/build"

if [ ! -f "${BUILD_DIR}/radagent_vis" ]; then
    echo "Building radagent_vis..."
    mkdir -p "${BUILD_DIR}" && cd "${BUILD_DIR}" && cmake .. && make -j$(nproc)
fi

echo "Launching RadAgent 3D Visualization..."
exec env -i \
    HOME="$HOME" \
    DISPLAY="$DISPLAY" \
    XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
    PATH="/usr/bin:/bin:/usr/sbin:/sbin" \
    "${BUILD_DIR}/radagent_vis" "$@"
