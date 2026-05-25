import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from src import config
from src.dedup import filter_duplicates, mark_seen, get_monthly_doc, save_monthly_doc
from src.feishu.client import create_document, add_blocks, get_document_url
from src.feishu.doc_builder import build_monthly_header, build_daily_section
from src.models import NewsItem
from src.sources.ai_news import AINewsSource
from src.sources.github_trending import GitHubTrendingSource
from src.sources.world_news import WorldNewsSource
from src.summarizer import summarize_batch, filter_tech_only, summarize_github_batch
from src.utils import setup_logging

logger = logging.getLogger(__name__)

SOURCES = [
    AINewsSource(),
    GitHubTrendingSource(),
    WorldNewsSource(),
]


def _collect_news() -> dict[str, list[NewsItem]]:
    results: dict[str, list[NewsItem]] = {}
    with ThreadPoolExecutor(max_workers=len(SOURCES)) as executor:
        futures = {
            executor.submit(source.fetch): source.name
            for source in SOURCES
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                items = future.result()
                logger.info("Source '%s' returned %d items", name, len(items))
            except Exception:
                logger.error("Source '%s' failed completely", name, exc_info=True)
                items = []
            results[name] = items
    return results


def _apply_dedup(results: dict[str, list[NewsItem]]) -> dict[str, list[NewsItem]]:
    deduped: dict[str, list[NewsItem]] = {}
    for name, items in results.items():
        fresh = filter_duplicates(items)
        for item in fresh:
            mark_seen(item.url)
        deduped[name] = fresh
        logger.info("Source '%s': %d items after dedup (removed %d)", name, len(fresh), len(items) - len(fresh))
    return deduped


def main() -> int:
    setup_logging(config.LOG_LEVEL)

    if not config.FEISHU_APP_ID or not config.FEISHU_APP_SECRET:
        logger.error("FEISHU_APP_ID and FEISHU_APP_SECRET must be set")
        return 1

    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    month_str = now.strftime("%Y-%m")

    # Collect and dedup news
    logger.info("Starting news collection from %d sources", len(SOURCES))
    results = _collect_news()

    # Filter AI news to tech-only (new models, tools, research, products)
    if results.get("ai_news"):
        results["ai_news"] = filter_tech_only(results["ai_news"], config.AI_NEWS_LIMIT)

    results = _apply_dedup(results)

    total_items = sum(len(v) for v in results.values())
    if total_items == 0:
        logger.warning("No news items collected from any source")

    # Enrich descriptions
    for name in ["ai_news", "world_news"]:
        if results.get(name):
            logger.info("Summarizing %d items for %s", len(results[name]), name)
            results[name] = summarize_batch(results[name], name)

    # GitHub Chinese summaries
    if results.get("github_trending"):
        logger.info("Generating Chinese summaries for %d GitHub repos", len(results["github_trending"]))
        results["github_trending"] = summarize_github_batch(results["github_trending"])

    # Build today's content blocks
    daily_blocks = build_daily_section(results, date_str)
    logger.info("Built %d blocks for today", len(daily_blocks))

    # Get or create the monthly document
    try:
        existing = get_monthly_doc(month_str)
        if existing:
            doc_id, doc_url = existing
            logger.info("Using existing monthly doc: %s", doc_url)
        else:
            # Create new monthly document with header + first day
            doc_title = f"Daily News Digest - {month_str}"
            doc_id = create_document(doc_title)
            doc_url = get_document_url(doc_id)

            header_blocks = build_monthly_header(month_str)
            add_blocks(doc_id, header_blocks)
            save_monthly_doc(month_str, doc_id, doc_url)
            logger.info("Created new monthly doc: %s", doc_url)

        # Append today's content
        add_blocks(doc_id, daily_blocks)
        logger.info("Appended today's digest to monthly doc")
        print(f"Document URL: {doc_url}")
        return 0
    except Exception:
        logger.error("Failed to publish to Feishu", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
