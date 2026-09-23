"""Base scraper interface and abstract class for job portals."""

from __future__ import annotations

from abc import ABC, abstractmethod
import logging
from typing import List, Optional

from job_hunter.client import HttpClient
from job_hunter.models import NormalizedVacancy

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """Abstract base class for all job board scrapers."""

    name: str = "base"
    base_url: str = ""

    def __init__(self, client: Optional[HttpClient] = None):
        self.client = client or HttpClient()

    @abstractmethod
    def search(self, query: str, max_pages: int = 2) -> List[NormalizedVacancy]:
        """Search job vacancies matching query string across up to max_pages.

        Args:
            query: Keywords or job title to search.
            max_pages: Maximum number of result pages to traverse.

        Returns:
            List of NormalizedVacancy instances.
        """
        pass

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} portal='{self.name}'>"
