"""Configuration for WeChat public account scraper."""

from pathlib import Path

# Target account
ACCOUNT_NAME = "心兰相随tcad"
ACCOUNT_BIZ = ""  # Will be auto-detected from article pages

# Rate limiting (seconds)
DELAY_MIN = 2.0
DELAY_MAX = 5.0
IMAGE_DELAY = 0.5
DELAY_SOGOU_MIN = 3.0
DELAY_SOGOU_MAX = 7.0

# Extraction
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
SAVE_EVERY_N = 10  # Save progress every N articles

# User agents (rotated)
USER_AGENTS = [
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]

# Paths
WECHAT_SCRAPER_DIR = Path(__file__).parent
DATA_DIR = WECHAT_SCRAPER_DIR / "data"
ARTICLES_DIR = DATA_DIR / "articles"
IMAGES_DIR = DATA_DIR / "images"
URL_LIST_PATH = DATA_DIR / "url_list.json"
JSONL_OUTPUT_PATH = DATA_DIR / "wechat_articles.jsonl"

# RAG pipeline paths
TCAD_RAG_DIR = WECHAT_SCRAPER_DIR.parent
BUILD_INDEX_SCRIPT = TCAD_RAG_DIR / "build_index.py"
RAG_DATA_DIR = TCAD_RAG_DIR / "data"

# Sogou search
SOGOU_SEARCH_URL = "https://weixin.sogou.com/weixin"
SOGOU_ACCOUNT_URL = "https://weixin.sogou.com/weixin?type=1&query={account}&ie=utf8"
