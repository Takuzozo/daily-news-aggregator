from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class NewsItem:
    title: str
    url: str
    description: str
    source: str  # "ai_news", "github_trending", "world_news"
    published_at: datetime | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def id(self) -> str:
        import hashlib
        return hashlib.sha256(self.url.encode()).hexdigest()[:16]
