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
WORK_DIR = Path("/tmp/radagent_work")

# Build
CMAKE_TIMEOUT = 120
RUN_TIMEOUT = 300
MAX_RETRIES = 3
