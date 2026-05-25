from abc import ABC, abstractmethod
from src.models import NewsItem


class NewsSource(ABC):
    @abstractmethod
    def fetch(self) -> list[NewsItem]:
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    def limit(self) -> int:
        return 10
