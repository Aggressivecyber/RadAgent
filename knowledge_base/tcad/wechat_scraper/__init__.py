"""WeChat public account article scraper for TCAD RAG pipeline."""

from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
ARTICLES_DIR = DATA_DIR / "articles"
IMAGES_DIR = DATA_DIR / "images"
URL_LIST_PATH = DATA_DIR / "url_list.json"
JSONL_OUTPUT_PATH = DATA_DIR / "wechat_articles.jsonl"


def setup_directories() -> None:
    """Create all required data directories."""
    for d in [DATA_DIR, ARTICLES_DIR, IMAGES_DIR]:
        d.mkdir(parents=True, exist_ok=True)
