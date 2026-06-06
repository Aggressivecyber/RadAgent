"""URL collection and management for WeChat articles.

Manages a persistent URL list with status tracking, deduplication,
and multiple discovery methods (manual, Sogou search).
"""

import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

from . import config

logger = logging.getLogger(__name__)


class URLStatus(str, Enum):
    PENDING = "pending"
    SCRAPED = "scraped"
    FAILED = "failed"


@dataclass
class URLEntry:
    url: str
    status: URLStatus = URLStatus.PENDING
    discovered_at: str = ""
    source: str = "manual"  # manual, sogou, mitmproxy
    title: str = ""
    fail_count: int = 0

    def __post_init__(self) -> None:
        if not self.discovered_at:
            self.discovered_at = time.strftime("%Y-%m-%dT%H:%M:%S")


class URLList:
    """Persistent URL list with dedup and status tracking."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or config.URL_LIST_PATH
        self._entries: dict[str, URLEntry] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data:
                entry = URLEntry(**item)
                self._entries[entry.url] = entry
            logger.info("Loaded %d URLs from %s", len(self._entries), self.path)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = [asdict(e) for e in self._entries.values()]
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp.replace(self.path)
        logger.info("Saved %d URLs to %s", len(self._entries), self.path)

    def add_urls(self, urls: list[str], source: str = "manual") -> int:
        """Add URLs with deduplication. Returns count of newly added."""
        added = 0
        for url in urls:
            url = url.strip()
            if not url or "mp.weixin.qq.com" not in url:
                continue
            # Normalize URL: remove tracking params
            url = _normalize_url(url)
            if url not in self._entries:
                self._entries[url] = URLEntry(url=url, source=source)
                added += 1
        if added > 0:
            self.save()
        return added

    def mark_scraped(self, url: str, title: str = "") -> None:
        if url in self._entries:
            self._entries[url].status = URLStatus.SCRAPED
            self._entries[url].title = title

    def mark_failed(self, url: str) -> None:
        if url in self._entries:
            entry = self._entries[url]
            entry.fail_count += 1
            if entry.fail_count >= config.MAX_RETRIES:
                entry.status = URLStatus.FAILED
                logger.warning("URL failed %d times, marking as failed: %s",
                               entry.fail_count, url)
            else:
                entry.status = URLStatus.PENDING

    def get_pending(self) -> list[URLEntry]:
        return [e for e in self._entries.values()
                if e.status == URLStatus.PENDING]

    def get_stats(self) -> dict[str, int]:
        stats = {"total": len(self._entries), "pending": 0, "scraped": 0, "failed": 0}
        for e in self._entries.values():
            stats[e.status.value] += 1
        return stats

    @property
    def scraped_urls(self) -> set[str]:
        return {url for url, e in self._entries.items()
                if e.status == URLStatus.SCRAPED}


def _normalize_url(url: str) -> str:
    """Remove tracking parameters from WeChat article URL."""
    # Keep only the essential path: mp.weixin.qq.com/s/xxxxx
    match = re.match(r"(https?://mp\.weixin\.qq\.com/s/\S+?)(?:&|\?|$)", url)
    if match:
        base = match.group(1)
        # Remove query params, keep just /s/<id>
        return base.split("?")[0].split("&")[0]
    return url


def collect_from_sogou(account_name: str, max_pages: int = 5) -> list[str]:
    """Discover article URLs via Sogou WeChat search.

    WARNING: Sogou aggressively blocks bots. This is a best-effort
    supplementary discovery method.
    """
    urls: list[str] = []
    headers = {"User-Agent": config.USER_AGENTS[0]}

    for page in range(1, max_pages + 1):
        params = {
            "type": "1",  # Search by account
            "query": account_name,
            "ie": "utf8",
            "page": str(page),
        }
        try:
            resp = requests.get(
                config.SOGOU_SEARCH_URL,
                params=params,
                headers=headers,
                timeout=config.REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.warning("Sogou request failed (page %d): %s", page, e)
            break

        if "验证码" in resp.text or "antispider" in resp.url:
            logger.warning("Sogou anti-bot detected on page %d. Stopping.", page)
            break

        soup = BeautifulSoup(resp.text, "lxml")
        page_urls = _extract_urls_from_sogou(soup)
        if not page_urls:
            logger.info("No more results on Sogou page %d", page)
            break
        urls.extend(page_urls)
        logger.info("Sogou page %d: found %d URLs", page, len(page_urls))
        time.sleep(config.DELAY_SOGOU_MIN)

    return list(set(urls))


def _extract_urls_from_sogou(soup: BeautifulSoup) -> list[str]:
    """Extract WeChat article URLs from Sogou search results page."""
    urls: list[str] = []
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if "mp.weixin.qq.com" in href:
            urls.append(href)
    # Also check for redirect URLs
    for div in soup.find_all(class_="txt-box"):
        a = div.find("a", href=True)
        if a and "mp.weixin.qq.com" in a["href"]:
            urls.append(a["href"])
    return urls


def add_urls_from_file(file_path: str, url_list: URLList, source: str = "manual") -> int:
    """Read URLs from a text file (one per line) and add to URL list."""
    path = Path(file_path)
    if not path.exists():
        logger.error("File not found: %s", file_path)
        return 0

    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    urls = [line.strip() for line in lines if line.strip()]
    return url_list.add_urls(urls, source=source)
