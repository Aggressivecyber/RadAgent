"""Image downloader for WeChat articles.

Downloads images referenced in articles, stores them locally,
and handles deduplication via content hashing.
"""

import hashlib
import logging
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

from . import config

logger = logging.getLogger(__name__)


class ImageDownloader:
    """Download and store article images locally."""

    def __init__(self, output_dir: Path | None = None) -> None:
        self.output_dir = output_dir or config.IMAGES_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": config.USER_AGENTS[0],
            "Referer": "https://mp.weixin.qq.com/",
        })
        self._hash_cache: set[str] = set()

    def download_image(self, url: str, article_id: str, index: int) -> str | None:
        """Download a single image. Returns local path or None on failure."""
        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.warning("Failed to download image %d: %s", index, e)
            return None

        content = resp.content
        content_hash = hashlib.sha256(content).hexdigest()[:16]

        # Dedup
        if content_hash in self._hash_cache:
            logger.debug("Duplicate image skipped: %s", content_hash)
            existing = list(self.output_dir.glob(f"*_{content_hash}.*"))
            if existing:
                return str(existing[0])
        self._hash_cache.add(content_hash)

        # Determine extension
        ext = _guess_extension(url, resp.headers.get("Content-Type", ""))
        filename = f"{article_id}_{index}_{content_hash}{ext}"
        filepath = self.output_dir / filename

        filepath.write_bytes(content)
        logger.debug("Downloaded: %s (%d bytes)", filename, len(content))
        return str(filepath)

    def download_article_images(
        self,
        article_id: str,
        image_urls: list[str],
    ) -> list[str]:
        """Download all images for an article. Returns list of local paths."""
        local_paths: list[str] = []

        for i, url in enumerate(image_urls):
            path = self.download_image(url, article_id, i)
            if path:
                local_paths.append(path)
            time.sleep(config.IMAGE_DELAY)

        if local_paths:
            logger.info("Downloaded %d/%d images for article %s",
                        len(local_paths), len(image_urls), article_id)
        return local_paths


def _guess_extension(url: str, content_type: str) -> str:
    """Guess file extension from URL or content type."""
    # Try URL path first
    parsed = urlparse(url)
    path = parsed.path.lower()
    for ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"):
        if path.endswith(ext):
            return ext

    # Fallback to content type
    ct = content_type.lower()
    if "png" in ct:
        return ".png"
    if "gif" in ct:
        return ".gif"
    if "webp" in ct:
        return ".webp"
    if "svg" in ct:
        return ".svg"
    return ".jpg"  # Default
