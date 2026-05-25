import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

import feedparser
import requests

from src import config
from src.models import NewsItem
from src.sources.base import NewsSource
from src.utils import normalize_url, retry_with_backoff

logger = logging.getLogger(__name__)


class AINewsSource(NewsSource):
    name = "ai_news"

    @property
    def limit(self) -> int:
        # Return 3x the final limit for tech filtering
        return config.AI_NEWS_LIMIT * 3

    def fetch(self) -> list[NewsItem]:
        items: list[NewsItem] = []
        seen_urls: set[str] = set()
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

        with ThreadPoolExecutor(max_workers=len(config.AI_FEED_URLS)) as executor:
            futures = {
                executor.submit(self._fetch_feed, url): url
                for url in config.AI_FEED_URLS
            }
            for future in as_completed(futures):
                url = futures[future]
                try:
                    feed_items = future.result()
                    logger.info("Fetched %d items from %s", len(feed_items), url)
                    for item in feed_items:
                        norm = normalize_url(item.url)
                        if norm not in seen_urls and (item.published_at is None or item.published_at >= cutoff):
                            seen_urls.add(norm)
                            items.append(item)
                except Exception:
                    logger.warning("Failed to fetch feed: %s", url, exc_info=True)

        # Fallback to Google News RSS if too few results
        if len(items) < config.AI_NEWS_LIMIT:
            logger.info("Fewer than %d items from primary feeds, trying fallback", config.AI_NEWS_LIMIT)
            try:
                fallback_items = self._fetch_feed(config.AI_FALLBACK_URL)
                for item in fallback_items:
                    norm = normalize_url(item.url)
                    if norm not in seen_urls and (item.published_at is None or item.published_at >= cutoff):
                        seen_urls.add(norm)
                        items.append(item)
            except Exception:
                logger.warning("Failed to fetch fallback feed", exc_info=True)

        items.sort(key=lambda x: x.published_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        logger.info("AI news: %d total unique items, returning top %d", len(items), min(self.limit, len(items)))
        return items[:self.limit]

    @staticmethod
    @retry_with_backoff(max_retries=3, base_delay=1.0)
    def _fetch_feed(url: str) -> list[NewsItem]:
        resp = requests.get(
            url,
            timeout=15,
            headers={"User-Agent": "DailyNewsAggregator/1.0 (news bot)"},
        )
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        items: list[NewsItem] = []
        for entry in feed.entries:
            title = entry.get("title", "").strip()
            link = entry.get("link", "")
            summary = entry.get("summary", "") or entry.get("description", "")
            # Strip HTML tags from summary, but keep it longer
            import re
            summary = re.sub(r"<[^>]+>", "", summary).strip()
            if len(summary) > 1000:
                summary = summary[:1000] + "..."

            published = None
            if entry.get("published_parsed"):
                try:
                    published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                except (ValueError, TypeError):
                    pass

            if title and link:
                items.append(NewsItem(
                    title=title,
                    url=link,
                    description=summary,
                    source="ai_news",
                    published_at=published,
                ))
        return items
