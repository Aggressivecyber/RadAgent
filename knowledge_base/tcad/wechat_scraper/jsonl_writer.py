"""JSONL writer for TCAD RAG pipeline compatibility.

Converts scraped articles to JSONL format matching existing
manuals.jsonl schema used by build_index.py.
"""

import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Optional

from . import config

logger = logging.getLogger(__name__)

# Schema must match: source, file_path, title, content, metadata
JSONL_FIELDS = ("source", "file_path", "title", "content", "metadata")


class JSONLWriter:
    """Write articles to JSONL compatible with TCAD RAG pipeline."""

    def __init__(self, output_path: Optional[Path] = None) -> None:
        self.output_path = output_path or config.JSONL_OUTPUT_PATH
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._existing_urls: set[str] = self._load_existing_urls()

    def _load_existing_urls(self) -> set[str]:
        """Load URLs already written to JSONL to avoid duplicates."""
        urls: set[str] = set()
        if not self.output_path.exists():
            return urls
        with open(self.output_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    meta = json.loads(record.get("metadata", "{}"))
                    if "url" in meta:
                        urls.add(meta["url"])
                except (json.JSONDecodeError, KeyError):
                    continue
        return urls

    def write_article(self, article: dict) -> bool:
        """Write a single article to JSONL. Returns True if written."""
        url = article.get("url", "")
        if url in self._existing_urls:
            logger.debug("Skipping duplicate: %s", url[:80])
            return False

        record = {
            "source": "wechat_mp",
            "file_path": f"mp.weixin.qq.com/s/{_extract_article_id(url)}",
            "title": article.get("title", ""),
            "content": article.get("content_markdown", "") or
                       article.get("content_text", ""),
            "metadata": json.dumps({
                "type": "wechat_mp",
                "account": article.get("account", config.ACCOUNT_NAME),
                "author": article.get("author", ""),
                "publish_date": article.get("publish_date", ""),
                "url": url,
                "digest": article.get("digest", ""),
                "format": "markdown",
                "image_count": len(article.get("local_images", [])),
            }, ensure_ascii=False),
        }

        with open(self.output_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        self._existing_urls.add(url)
        return True

    def write_batch(self, articles: list[dict]) -> int:
        """Write multiple articles. Returns count actually written."""
        written = 0
        for article in articles:
            if self.write_article(article):
                written += 1
        logger.info("Wrote %d/%d articles to %s",
                    written, len(articles), self.output_path)
        return written

    def deduplicate(self) -> int:
        """Remove duplicate entries by URL. Returns count removed."""
        if not self.output_path.exists():
            return 0

        seen_urls: set[str] = set()
        kept: list[str] = []

        with open(self.output_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    meta = json.loads(record.get("metadata", "{}"))
                    url = meta.get("url", "")
                except (json.JSONDecodeError, KeyError):
                    kept.append(line)
                    continue

                if url not in seen_urls:
                    seen_urls.add(url)
                    kept.append(line)

        removed = sum(1 for l in open(self.output_path) if l.strip()) - len(kept)
        if removed > 0:
            with open(self.output_path, "w", encoding="utf-8") as f:
                f.write("\n".join(kept) + "\n")
            logger.info("Deduplicated: removed %d entries", removed)
        return removed


def trigger_index_rebuild(skip_preprocess: bool = True) -> bool:
    """Run build_index.py to ingest scraped articles into RAG index."""
    script = config.BUILD_INDEX_SCRIPT
    if not script.exists():
        logger.error("build_index.py not found at %s", script)
        return False

    cmd = [sys.executable, str(script)]
    if skip_preprocess:
        cmd.append("--skip-preprocess")

    logger.info("Running index build: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(config.TCAD_RAG_DIR))

    if result.returncode == 0:
        logger.info("Index build completed successfully")
    else:
        logger.error("Index build failed:\n%s\n%s", result.stdout[-500:], result.stderr[-500:])

    return result.returncode == 0


def _extract_article_id(url: str) -> str:
    """Extract article ID from WeChat URL."""
    import re
    match = re.search(r"/s/([A-Za-z0-9_-]+)", url)
    return match.group(1) if match else "unknown"
