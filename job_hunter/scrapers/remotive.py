"""Remotive public API scraper consuming remotive.com/api/remote-jobs."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

from job_hunter.client import HttpClient
from job_hunter.models import NormalizedVacancy
from job_hunter.normalizer import normalize_vacancy
from job_hunter.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class RemotiveScraper(BaseScraper):
    """Scraper for Remotive API (remotive.com)."""

    name: str = "remotive"
    base_url: str = "https://remotive.com"
    api_endpoint: str = "https://remotive.com/api/remote-jobs"

    def __init__(self, client: Optional[HttpClient] = None):
        super().__init__(client=client)

    def search(self, query: str, max_pages: int = 1) -> List[NormalizedVacancy]:
        """Search Remotive API for remote jobs matching query."""
        params = {"search": query.strip()}
        url = f"{self.api_endpoint}?{urlencode(params)}"
        logger.info(f"[Remotive] Querying endpoint: {url}")

        data = self.client.get_json(url)
        if not data or not isinstance(data, dict):
            logger.warning("[Remotive] No valid JSON response returned")
            return []

        return self.parse_api_response(data)

    def parse_api_response(self, data: Dict[str, Any]) -> List[NormalizedVacancy]:
        """Parse Remotive JSON response payload into NormalizedVacancy list."""
        jobs = data.get("jobs", [])
        if not isinstance(jobs, list):
            return []

        results: List[NormalizedVacancy] = []
        for job in jobs:
            if not isinstance(job, dict):
                continue

            try:
                raw_title = job.get("title", "")
                raw_url = job.get("url", "")
                if not raw_title or not raw_url:
                    continue

                raw_company = job.get("company_name", "Confidencial")
                raw_location = job.get("candidate_required_location") or "Worldwide (Remoto)"
                raw_salary = job.get("salary")
                raw_date = job.get("publication_date")
                raw_desc = job.get("description", "")
                external_id = str(job.get("id", ""))

                vacancy = normalize_vacancy(
                    title=raw_title,
                    company=raw_company,
                    direct_url=raw_url,
                    full_description=raw_desc,
                    source_portal=self.name,
                    publication_date=raw_date,
                    location=raw_location,
                    modality="remoto",
                    salary_range=raw_salary,
                    raw_snippet=raw_title,
                    extra_metadata={
                        "external_id": external_id,
                        "category": job.get("category"),
                        "tags": job.get("tags", []),
                    },
                )
                results.append(vacancy)

            except Exception as e:
                logger.warning(f"[Remotive] Failed to parse job item: {e}")
                continue

        return results
