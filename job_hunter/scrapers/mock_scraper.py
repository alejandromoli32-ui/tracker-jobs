"""Mock scraper providing deterministic test dataset from mock_vacancies.json."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from job_hunter.client import HttpClient
from job_hunter.models import NormalizedVacancy
from job_hunter.normalizer import normalize_vacancy
from job_hunter.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

DEFAULT_FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "mock_vacancies.json"


import unicodedata

def _strip_accents(text: str) -> str:
    """Strip diacritics / accent marks from string for robust matching."""
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


class MockScraper(BaseScraper):
    """Scraper serving verified offline fixture dataset for deterministic tests and offline runs."""

    name: str = "mock"
    base_url: str = "https://mock.portal.local"

    def __init__(
        self,
        fixture_path: Optional[Path] = None,
        client: Optional[HttpClient] = None,
    ):
        super().__init__(client=client)
        self.fixture_path = Path(fixture_path) if fixture_path else DEFAULT_FIXTURE_PATH
        self._cached_vacancies: Optional[List[NormalizedVacancy]] = None

    def _load_fixtures(self) -> List[NormalizedVacancy]:
        """Load fixture data from JSON file and instantiate NormalizedVacancy objects."""
        if self._cached_vacancies is not None:
            return self._cached_vacancies

        if not self.fixture_path.exists():
            logger.warning(f"[MockScraper] Fixture file not found at {self.fixture_path}")
            return []

        try:
            with open(self.fixture_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)

            vacancies: List[NormalizedVacancy] = []
            for item in raw_data:
                if isinstance(item, dict):
                    extra = item.get("extra_metadata") or item.get("metadata") or {}
                    vac = normalize_vacancy(
                        title=item.get("title", ""),
                        company=item.get("company"),
                        direct_url=item.get("direct_url", ""),
                        full_description=item.get("full_description", ""),
                        source_portal=item.get("source_portal", "mock"),
                        publication_date=item.get("publication_date"),
                        location=item.get("location"),
                        modality=item.get("modality"),
                        salary_range=item.get("salary_range"),
                        raw_snippet=item.get("raw_snippet"),
                        extra_metadata=extra,
                        custom_id=item.get("id"),
                    )
                    vacancies.append(vac)

            self._cached_vacancies = vacancies
            return vacancies
        except Exception as e:
            logger.error(f"[MockScraper] Error loading fixture data: {e}")
            return []

    def search(self, query: str, max_pages: int = 1) -> List[NormalizedVacancy]:
        """Return vacancies matching search query keywords, or all if query is broad."""
        all_vacancies = self._load_fixtures()
        q_clean = _strip_accents(query.strip().lower())

        if not q_clean or q_clean == "*":
            return list(all_vacancies)

        # Keyword matching with accent stripping
        q_tokens = [tok for tok in q_clean.split() if len(tok) > 2]
        if not q_tokens:
            return list(all_vacancies)

        matched: List[NormalizedVacancy] = []
        for vac in all_vacancies:
            raw_text = f"{vac.title} {vac.full_description} {vac.company} {vac.location}"
            searchable = _strip_accents(raw_text.lower())
            if any(tok in searchable for tok in q_tokens):
                matched.append(vac)

        return matched if matched else list(all_vacancies)
