import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# DeepSeek API
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = "deepseek-chat"

# Geant4
GEANT4_INSTALL = Path("/usr/local/geant4")
GEANT4_SOURCE_SCRIPT = "/etc/profile.d/geant4.sh"
TEMPLATES_DIR = Path(__file__).parent / "templates"
DATA_DIR = Path(__file__).parent / "data"
WORKSPACE_DIR = Path(__file__).parent.parent / "workspace"

# Build
CMAKE_TIMEOUT = 120
MAX_RETRIES = 3

# Logging
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_LEVEL = "DEBUG"

# Memory (L2+L3)
MEMORY_DIR = Path(__file__).parent / "memory"
MEMORY_DB = MEMORY_DIR / "store.db"
CHECKPOINT_DB = MEMORY_DIR / "checkpoints.db"

# Default user
DEFAULT_USER = os.environ.get("RADAGENT_USER", "default")

# ─── 模型路由：三档 ──────────────────────────────────────────
# light  → 快速提取（意图解析、参数解析、反馈解析）
# standard → 通用推理（屏蔽设计、场景生成、报告生成）
# premium → 高质量评估（门禁评分、质量审核）
# 当前三档统一用 DeepSeek，后续可按档位配置不同模型/参数
MODEL_TIERS = {
    "light": {
        "model": DEEPSEEK_MODEL,
        "base_url": DEEPSEEK_BASE_URL,
        "api_key": DEEPSEEK_API_KEY,
        "temperature": 0,
    },
    "standard": {
        "model": DEEPSEEK_MODEL,
        "base_url": DEEPSEEK_BASE_URL,
        "api_key": DEEPSEEK_API_KEY,
        "temperature": 0,
    },
    "premium": {
        "model": DEEPSEEK_MODEL,
        "base_url": DEEPSEEK_BASE_URL,
        "api_key": DEEPSEEK_API_KEY,
        "temperature": 0,
    },
}
