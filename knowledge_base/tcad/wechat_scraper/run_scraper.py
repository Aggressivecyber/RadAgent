#!/usr/bin/env python3
"""WeChat article scraper CLI for TCAD RAG pipeline.

Usage:
    python3 run_scraper.py discover             # Search Sogou for article URLs
    python3 run_scraper.py add-urls --file URLS  # Add URLs from text file
    python3 run_scraper.py extract [--max N]     # Extract articles from pending URLs
    python3 run_scraper.py status                # Show URL list statistics
    python3 run_scraper.py export                # Export scraped articles to JSONL
    python3 run_scraper.py ingest                # Build RAG index from JSONL
    python3 run_scraper.py full-run              # discover -> extract -> export -> ingest
"""

import argparse
import json
import logging
import signal
import sys
from dataclasses import asdict
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from wechat_scraper import setup_directories
from wechat_scraper.article_extractor import ArticleExtractor, _url_to_id
from wechat_scraper.config import ACCOUNT_NAME
from wechat_scraper.image_downloader import ImageDownloader
from wechat_scraper.jsonl_writer import JSONLWriter, trigger_index_rebuild
from wechat_scraper.url_collector import URLList, add_urls_from_file, collect_from_sogou

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_scraper")

# Graceful shutdown
_shutdown = False


def _signal_handler(sig, frame):
    global _shutdown
    _shutdown = True
    logger.info("Received signal %s, shutting down gracefully...", sig)


signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


def cmd_discover(args: argparse.Namespace) -> None:
    """Discover article URLs via Sogou search."""
    url_list = URLList()
    logger.info("Searching Sogou for account: %s", ACCOUNT_NAME)
    urls = collect_from_sogou(ACCOUNT_NAME, max_pages=args.pages)
    added = url_list.add_urls(urls, source="sogou")
    logger.info("Added %d new URLs (total: %d)", added, len(url_list._entries))


def cmd_add_urls(args: argparse.Namespace) -> None:
    """Add URLs from a text file."""
    url_list = URLList()
    added = add_urls_from_file(args.file, url_list, source="manual")
    logger.info("Added %d new URLs from %s", added, args.file)
    _print_stats(url_list)


def cmd_extract(args: argparse.Namespace) -> None:
    """Extract articles from pending URLs."""
    url_list = URLList()
    stats = url_list.get_stats()
    logger.info("Pending: %d articles to extract", stats["pending"])

    if stats["pending"] == 0:
        logger.info("No pending URLs. Add URLs first with 'add-urls' or 'discover'.")
        return

    extractor = ArticleExtractor(url_list=url_list)
    downloader = ImageDownloader()

    pending = url_list.get_pending()
    urls = [e.url for e in pending]
    if args.max > 0:
        urls = urls[:args.max]

    articles = []
    for i, url in enumerate(urls):
        if _shutdown:
            logger.info("Shutdown requested, stopping after %d articles", len(articles))
            break

        article = extractor.extract_article(url)
        if article:
            # Download images
            article_id = _url_to_id(article.url)
            local_imgs = downloader.download_article_images(
                article_id, article.image_urls
            )
            article.local_images = local_imgs

            # Replace image URLs in markdown with local paths
            if local_imgs:
                content = article.content_markdown
                for j, orig_url in enumerate(article.image_urls):
                    if j < len(local_imgs):
                        content = content.replace(orig_url, local_imgs[j])
                article.content_markdown = content

            articles.append(asdict(article))

        progress = f"[{i + 1}/{len(urls)}]"
        if article:
            logger.info("%s OK: %s", progress, article.title[:60])
        else:
            logger.info("%s SKIP: %s", progress, url[:60])

    logger.info("Extracted %d articles total", len(articles))
    _print_stats(url_list)


def cmd_status(args: argparse.Namespace) -> None:
    """Show URL list statistics."""
    url_list = URLList()
    _print_stats(url_list)

    # Check for scraped articles on disk
    articles_dir = Path(__file__).parent / "data" / "articles"
    json_files = list(articles_dir.glob("*.json")) if articles_dir.exists() else []
    jsonl_path = Path(__file__).parent / "data" / "wechat_articles.jsonl"
    jsonl_count = 0
    if jsonl_path.exists():
        with open(jsonl_path) as f:
            jsonl_count = sum(1 for l in f if l.strip())

    print(f"\n  Articles on disk: {len(json_files)}")
    print(f"  JSONL records:    {jsonl_count}")


def cmd_export(args: argparse.Namespace) -> None:
    """Export scraped articles to JSONL for RAG ingestion."""
    articles_dir = Path(__file__).parent / "data" / "articles"
    json_files = sorted(articles_dir.glob("*.json"))

    if not json_files:
        logger.error("No scraped articles found. Run 'extract' first.")
        return

    writer = JSONLWriter()
    count = 0
    for jf in json_files:
        with open(jf, "r", encoding="utf-8") as f:
            article = json.load(f)
        if writer.write_article(article):
            count += 1

    logger.info("Exported %d articles to JSONL", count)

    # Also run dedup
    removed = writer.deduplicate()
    if removed > 0:
        logger.info("Removed %d duplicates", removed)


def cmd_ingest(args: argparse.Namespace) -> None:
    """Build RAG index from exported JSONL."""
    jsonl_path = Path(__file__).parent / "data" / "wechat_articles.jsonl"
    if not jsonl_path.exists():
        logger.error("No JSONL file found. Run 'export' first.")
        return

    success = trigger_index_rebuild(skip_preprocess=True)
    if success:
        logger.info("RAG index updated successfully")
    else:
        logger.error("RAG index build failed")
        sys.exit(1)


def cmd_full_run(args: argparse.Namespace) -> None:
    """Run the full pipeline: discover -> extract -> export -> ingest."""
    # Discover
    logger.info("=== Phase 1: Discovery ===")
    cmd_discover(args)

    # Extract
    logger.info("=== Phase 2: Extraction ===")
    cmd_extract(args)

    # Export
    logger.info("=== Phase 3: Export ===")
    cmd_export(args)

    # Ingest
    if args.no_ingest:
        logger.info("Skipping ingestion (--no-ingest)")
    else:
        logger.info("=== Phase 4: Ingest ===")
        cmd_ingest(args)


def _print_stats(url_list: URLList) -> None:
    stats = url_list.get_stats()
    print(f"\n  URL List Status:")
    print(f"    Total:   {stats['total']}")
    print(f"    Pending: {stats['pending']}")
    print(f"    Scraped: {stats['scraped']}")
    print(f"    Failed:  {stats['failed']}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="WeChat article scraper for TCAD RAG"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # discover
    p_disc = sub.add_parser("discover", help="Search Sogou for article URLs")
    p_disc.add_argument("--pages", type=int, default=5, help="Max pages to search")

    # add-urls
    p_add = sub.add_parser("add-urls", help="Add URLs from text file")
    p_add.add_argument("--file", required=True, help="Text file with URLs (one per line)")

    # extract
    p_ext = sub.add_parser("extract", help="Extract articles from pending URLs")
    p_ext.add_argument("--max", type=int, default=0, help="Max articles to extract (0=all)")

    # status
    sub.add_parser("status", help="Show URL list statistics")

    # export
    sub.add_parser("export", help="Export scraped articles to JSONL")

    # ingest
    sub.add_parser("ingest", help="Build RAG index from JSONL")

    # full-run
    p_full = sub.add_parser("full-run", help="Run full pipeline")
    p_full.add_argument("--pages", type=int, default=5)
    p_full.add_argument("--max", type=int, default=0)
    p_full.add_argument("--no-ingest", action="store_true", help="Skip RAG ingestion")

    args = parser.parse_args()

    setup_directories()

    commands = {
        "discover": cmd_discover,
        "add-urls": cmd_add_urls,
        "extract": cmd_extract,
        "status": cmd_status,
        "export": cmd_export,
        "ingest": cmd_ingest,
        "full-run": cmd_full_run,
    }

    cmd_func = commands.get(args.command)
    if cmd_func:
        cmd_func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
