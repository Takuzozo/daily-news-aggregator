import logging
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

from src import config
from src.models import NewsItem
from src.sources.base import NewsSource
from src.utils import retry_with_backoff

logger = logging.getLogger(__name__)


class GitHubTrendingSource(NewsSource):
    name = "github_trending"

    @property
    def limit(self) -> int:
        return config.GITHUB_TRENDING_LIMIT

    def fetch(self) -> list[NewsItem]:
        items = self._scrape_trending()
        if len(items) == 0:
            logger.warning("Scraping returned no results, trying API fallback")
            items = self._api_fallback()
        return items[:self.limit]

    @retry_with_backoff(max_retries=3, base_delay=1.0)
    def _scrape_trending(self) -> list[NewsItem]:
        resp = requests.get(
            config.GITHUB_TRENDING_URL,
            timeout=15,
            headers={"User-Agent": "DailyNewsAggregator/1.0 (news bot)"},
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "html.parser")
        items: list[NewsItem] = []

        for article in soup.select("article.Box-row"):
            try:
                # Repo name and link
                h2 = article.select_one("h2.h3 a")
                if not h2:
                    continue
                href = h2.get("href", "").strip()
                full_name = href.strip("/")
                url = f"https://github.com{href}"

                # Description
                desc_el = article.select_one("p")
                description = desc_el.get_text(strip=True) if desc_el else ""

                # Stars gained today
                stars_today = ""
                stars_els = article.select("span.d-inline-block.float-sm-right")
                if stars_els:
                    stars_today = stars_els[-1].get_text(strip=True)

                # Language
                lang_el = article.select_one("span[itemprop='programmingLanguage']")
                language = lang_el.get_text(strip=True) if lang_el else ""

                # Total stars
                total_stars = ""
                for a in article.select("a"):
                    href_val = a.get("href", "")
                    if href_val.endswith("/stargazers"):
                        total_stars = a.get_text(strip=True)
                        break

                if full_name:
                    items.append(NewsItem(
                        title=full_name,
                        url=url,
                        description=description,
                        source="github_trending",
                        extra={
                            "stars_today": stars_today,
                            "stars_total": total_stars,
                            "language": language,
                        },
                    ))
            except Exception:
                logger.warning("Failed to parse a trending repo row", exc_info=True)

        logger.info("GitHub trending: scraped %d repos", len(items))
        return items

    def _api_fallback(self) -> list[NewsItem]:
        if not config.GH_TRENDING_TOKEN:
            logger.warning("No GH_TRENDING_TOKEN set, skipping API fallback")
            return []

        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        try:
            resp = requests.get(
                config.GITHUB_API_SEARCH_URL,
                params={
                    "q": f"created:>{yesterday}",
                    "sort": "stars",
                    "order": "desc",
                    "per_page": self.limit,
                },
                headers={
                    "Authorization": f"Bearer {config.GH_TRENDING_TOKEN}",
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "DailyNewsAggregator/1.0",
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            items: list[NewsItem] = []
            for repo in data.get("items", []):
                items.append(NewsItem(
                    title=repo.get("full_name", ""),
                    url=repo.get("html_url", ""),
                    description=repo.get("description", "") or "",
                    source="github_trending",
                    extra={
                        "stars_today": str(repo.get("stargazers_count", "")),
                        "stars_total": str(repo.get("stargazers_count", "")),
                        "language": repo.get("language", "") or "",
                    },
                ))
            logger.info("GitHub API fallback: %d repos", len(items))
            return items
        except Exception:
            logger.warning("GitHub API fallback failed", exc_info=True)
            return []
