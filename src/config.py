import os
from pathlib import Path


def _load_dotenv() -> None:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip()
            if key not in os.environ:
                os.environ[key] = value


_load_dotenv()


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


FEISHU_APP_ID = _env("FEISHU_APP_ID")
FEISHU_APP_SECRET = _env("FEISHU_APP_SECRET")
GH_TRENDING_TOKEN = _env("GH_TRENDING_TOKEN")

AI_NEWS_LIMIT = int(_env("AI_NEWS_LIMIT", "10"))
GITHUB_TRENDING_LIMIT = int(_env("GITHUB_TRENDING_LIMIT", "10"))
WORLD_NEWS_LIMIT = int(_env("WORLD_NEWS_LIMIT", "10"))

DEDUP_DAYS = int(_env("DEDUP_DAYS", "3"))
LOG_LEVEL = _env("LOG_LEVEL", "INFO")

AI_FEED_URLS = [
    # Tech-focused source
    "https://www.marktechpost.com/feed/",
    # General tech sources
    "https://techcrunch.com/feed/",
    "https://arstechnica.com/ai/feed/",
    "https://venturebeat.com/category/ai/feed/",
    "https://www.technologyreview.com/feed/",
    "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
]

AI_FALLBACK_URL = "https://news.google.com/rss/search?q=artificial+intelligence&hl=en-US&gl=US&ceid=US:en"

WORLD_FEED_URLS = [
    "http://feeds.bbci.co.uk/news/world/rss.xml",
    "http://feeds.bbci.co.uk/news/rss.xml",
    "https://www.theguardian.com/world/rss",
    "https://feeds.npr.org/1004/rss.xml",
    "https://www.aljazeera.com/xml/rss/all.xml",
]

WORLD_FALLBACK_URL = (
    "https://news.google.com/rss/topics/"
    "CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx1YlY4U0FtVnVHZ0pWVXlnQVAB"
    "?hl=en-US&gl=US&ceid=US:en"
)

GITHUB_TRENDING_URL = "https://github.com/trending?since=daily"
GITHUB_API_SEARCH_URL = "https://api.github.com/search/repositories"

DEEPSEEK_API_KEY = _env("DEEPSEEK_API_KEY")
SUMMARY_MODEL = _env("SUMMARY_MODEL", "deepseek-chat")

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DB_PATH = os.path.join(DATA_DIR, "seen_urls.db")
