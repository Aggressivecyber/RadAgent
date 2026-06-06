"""Article content extraction from WeChat public account pages.

Uses requests + BeautifulSoup to extract full article content
(title, author, date, body, images) from mp.weixin.qq.com/s/ URLs.
"""

import hashlib
import json
import logging
import random
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from . import config
from .url_collector import URLList

logger = logging.getLogger(__name__)


@dataclass
class Article:
    url: str
    title: str = ""
    author: str = ""
    account: str = ""
    publish_date: str = ""
    digest: str = ""
    content_html: str = ""
    content_text: str = ""
    content_markdown: str = ""
    image_urls: list[str] = None  # type: ignore[assignment]
    local_images: list[str] = None  # type: ignore[assignment]
    scraped_at: str = ""

    def __post_init__(self) -> None:
        if self.image_urls is None:
            self.image_urls = []
        if self.local_images is None:
            self.local_images = []
        if not self.scraped_at:
            self.scraped_at = time.strftime("%Y-%m-%dT%H:%M:%S")


class ArticleExtractor:
    """Extract full article content from WeChat article URLs."""

    def __init__(self, url_list: Optional[URLList] = None) -> None:
        self.url_list = url_list or URLList()
        self.session = requests.Session()
        self._rotate_ua()
        self.articles_dir = config.ARTICLES_DIR
        self.articles_dir.mkdir(parents=True, exist_ok=True)

    def _rotate_ua(self) -> None:
        self.session.headers.update({
            "User-Agent": random.choice(config.USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })

    def extract_article(self, url: str) -> Optional[Article]:
        """Extract full content from a single article URL."""
        article = Article(url=url)

        for attempt in range(config.MAX_RETRIES):
            try:
                self._rotate_ua()
                resp = self.session.get(url, timeout=config.REQUEST_TIMEOUT)
                resp.raise_for_status()
                break
            except requests.RequestException as e:
                logger.warning("Attempt %d/%d failed for %s: %s",
                               attempt + 1, config.MAX_RETRIES, url, e)
                if attempt + 1 == config.MAX_RETRIES:
                    self.url_list.mark_failed(url)
                    return None
                time.sleep(2 ** (attempt + 1))

        soup = BeautifulSoup(resp.text, "lxml")

        # Extract metadata
        article.title = _get_text(soup, "h1", id="activity-name") or \
                        _get_text(soup, "h1", class_="rich_media_title") or \
                        _get_meta(soup, "og:title") or ""
        article.title = article.title.strip()

        article.author = _get_text(soup, "span", class_="rich_media_meta_nickname") or \
                         _get_text(soup, "a", id="js_name") or ""
        article.author = article.author.strip()

        article.account = _get_text(soup, "a", id="js_name") or \
                          _get_meta(soup, "twitter:creator") or config.ACCOUNT_NAME
        article.account = article.account.strip()

        article.publish_date = _get_text(soup, "em", id="publish_time") or \
                               _get_meta(soup, "article:published_time") or ""
        article.publish_date = article.publish_date.strip()

        article.digest = _get_meta(soup, "og:description") or \
                         _get_text(soup, "p", class_="profile_signature") or ""

        # Extract main content
        content_div = soup.find("div", id="js_content") or \
                      soup.find("div", class_="rich_media_content") or \
                      soup.find("div", class_="rich_media_area_primary")

        if not content_div:
            logger.warning("No content div found for %s", url)
            self.url_list.mark_failed(url)
            return None

        # Extract images before cleaning
        article.image_urls = _extract_image_urls(content_div)

        # Clean and convert content
        article.content_html = _clean_html(content_div)
        article.content_text = content_div.get_text(separator="\n", strip=True)
        article.content_markdown = _html_to_markdown(content_div)

        # Save individual article JSON
        self._save_article(article)

        # Update URL list
        self.url_list.mark_scraped(url, article.title)

        logger.info("Extracted: %s (%s) [%d images]",
                     article.title[:50], article.publish_date,
                     len(article.image_urls))
        return article

    def extract_batch(
        self,
        urls: Optional[list[str]] = None,
        max_count: int = 0,
    ) -> list[Article]:
        """Extract multiple articles with rate limiting and progress saving.

        Args:
            urls: Specific URLs to extract. If None, extracts all pending.
            max_count: Max articles to extract in this batch. 0 = unlimited.
        """
        if urls is None:
            pending = self.url_list.get_pending()
            urls = [e.url for e in pending]

        articles: list[Article] = []
        count = 0

        for url in urls:
            if max_count > 0 and count >= max_count:
                break

            article = self.extract_article(url)
            if article:
                articles.append(article)
                count += 1

            # Periodic save
            if count > 0 and count % config.SAVE_EVERY_N == 0:
                self.url_list.save()
                logger.info("Progress: %d articles extracted", count)

            # Rate limit
            delay = random.uniform(config.DELAY_MIN, config.DELAY_MAX)
            time.sleep(delay)

        self.url_list.save()
        return articles

    def _save_article(self, article: Article) -> None:
        """Save article as individual JSON file."""
        article_id = _url_to_id(article.url)
        path = self.articles_dir / f"{article_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(article), f, ensure_ascii=False, indent=2)


def _get_text(soup: BeautifulSoup, tag: str, **kwargs) -> Optional[str]:
    """Safely extract text from a tag."""
    el = soup.find(tag, **kwargs)
    if isinstance(el, Tag):
        return el.get_text(strip=True)
    return None


def _get_meta(soup: BeautifulSoup, prop: str) -> Optional[str]:
    """Extract content from a meta tag by property name."""
    tag = soup.find("meta", attrs={"property": prop}) or \
          soup.find("meta", attrs={"name": prop})
    if isinstance(tag, Tag):
        return tag.get("content", "")
    return None


def _extract_image_urls(content_div: Tag) -> list[str]:
    """Extract all image URLs from content div."""
    urls: list[str] = []
    for img in content_div.find_all("img"):
        # WeChat uses data-src for lazy-loaded images
        src = img.get("data-src") or img.get("src", "")
        if src and src.startswith("http"):
            urls.append(src)
    return urls


def _clean_html(content_div: Tag) -> str:
    """Remove tracking/scripts/styles, keep semantic structure."""
    # Clone to avoid mutating original
    html = str(content_div)

    # Remove scripts, styles, tracking pixels
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all(["script", "style", "iframe", "noscript"]):
        tag.decompose()

    # Remove WeChat-specific tracking attributes
    for tag in soup.find_all(True):
        for attr in list(tag.attrs.keys()):
            if attr.startswith("data-") and attr not in ("data-src", "data-original"):
                del tag[attr]

    return str(soup)


def _html_to_markdown(content_div: Tag) -> str:
    """Convert WeChat article HTML to clean Markdown."""
    lines: list[str] = []

    for el in content_div.children:
        if not isinstance(el, Tag):
            text = str(el).strip()
            if text:
                lines.append(text)
            continue

        tag_name = el.name

        if tag_name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(tag_name[1])
            text = el.get_text(strip=True)
            lines.append(f"\n{'#' * level} {text}\n")

        elif tag_name == "p":
            text = _process_inline(el)
            if text.strip():
                lines.append(text.strip())

        elif tag_name == "pre":
            code = el.get_text()
            lines.append(f"\n```\n{code}\n```\n")

        elif tag_name == "img":
            src = el.get("data-src") or el.get("src", "")
            alt = el.get("alt", "")
            if src:
                lines.append(f"\n![{alt}]({src})\n")

        elif tag_name in ("ul", "ol"):
            for i, li in enumerate(el.find_all("li", recursive=False)):
                text = li.get_text(strip=True)
                if tag_name == "ol":
                    lines.append(f"{i + 1}. {text}")
                else:
                    lines.append(f"- {text}")

        elif tag_name == "table":
            md_table = _table_to_markdown(el)
            if md_table:
                lines.append(f"\n{md_table}\n")

        elif tag_name == "blockquote":
            text = el.get_text(strip=True)
            lines.append(f"> {text}")

        elif tag_name in ("strong", "b"):
            text = el.get_text(strip=True)
            lines.append(f"**{text}**")

        elif tag_name in ("em", "i"):
            text = el.get_text(strip=True)
            lines.append(f"*{text}*")

        elif tag_name == "br":
            lines.append("")

        elif tag_name == "section":
            # Recurse into section blocks
            section_text = _html_to_markdown(el)
            if section_text.strip():
                lines.append(section_text)

        else:
            text = _process_inline(el)
            if text.strip():
                lines.append(text.strip())

    return "\n\n".join(lines)


def _process_inline(el: Tag) -> str:
    """Process inline elements, preserving bold/italic/code."""
    parts: list[str] = []
    for child in el.children:
        if isinstance(child, str):
            parts.append(child)
        elif isinstance(child, Tag):
            if child.name in ("strong", "b"):
                parts.append(f"**{child.get_text()}**")
            elif child.name in ("em", "i"):
                parts.append(f"*{child.get_text()}*")
            elif child.name == "code":
                parts.append(f"`{child.get_text()}`")
            elif child.name == "br":
                parts.append("\n")
            elif child.name == "img":
                src = child.get("data-src") or child.get("src", "")
                alt = child.get("alt", "")
                if src:
                    parts.append(f"![{alt}]({src})")
            else:
                parts.append(child.get_text())
    return "".join(parts)


def _table_to_markdown(table: Tag) -> str:
    """Convert HTML table to Markdown table."""
    rows = table.find_all("tr")
    if not rows:
        return ""

    lines: list[str] = []
    for i, row in enumerate(rows):
        cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
        lines.append("| " + " | ".join(cells) + " |")
        if i == 0:
            lines.append("| " + " | ".join(["---"] * len(cells)) + " |")

    return "\n".join(lines)


def _url_to_id(url: str) -> str:
    """Generate a short ID from article URL."""
    return hashlib.md5(url.encode()).hexdigest()[:12]
