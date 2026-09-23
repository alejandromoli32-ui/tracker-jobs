"""Job aggregation engine orchestrating multi-portal scraping with error isolation and deduplication."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

from job_hunter.client import HttpClient
from job_hunter.models import NormalizedVacancy, ProfileConfig
from job_hunter.scrapers.base import BaseScraper
from job_hunter.scrapers.computrabajo import ComputrabajoScraper
from job_hunter.scrapers.elempleo import ElEmpleoScraper
from job_hunter.scrapers.linkedin import LinkedInScraper
from job_hunter.scrapers.mock_scraper import MockScraper
from job_hunter.scrapers.remotive import RemotiveScraper

logger = logging.getLogger(__name__)


class JobAggregationEngine:
    """Orchestrates job search across multiple portals with error isolation and deduplication."""

    def __init__(
        self,
        client: Optional[HttpClient] = None,
        custom_scrapers: Optional[Dict[str, BaseScraper]] = None,
    ):
        self.client = client or HttpClient()
        self.scrapers: Dict[str, BaseScraper] = {}

        # Register default scrapers
        self.register_scraper("computrabajo", ComputrabajoScraper(client=self.client))
        self.register_scraper("elempleo", ElEmpleoScraper(client=self.client))
        self.register_scraper("linkedin", LinkedInScraper(client=self.client))
        self.register_scraper("remotive", RemotiveScraper(client=self.client))
        self.register_scraper("mock", MockScraper(client=self.client))

        if custom_scrapers:
            for name, scraper in custom_scrapers.items():
                self.register_scraper(name, scraper)

        self.last_run_stats: Dict[str, Any] = {}

    def register_scraper(self, name: str, scraper: BaseScraper) -> None:
        """Register or override a scraper instance."""
        self.scrapers[name.strip().lower()] = scraper

    def get_scraper(self, name: str) -> Optional[BaseScraper]:
        """Retrieve registered scraper by portal name."""
        return self.scrapers.get(name.strip().lower())

    def run(
        self,
        queries: List[str],
        portals: Optional[List[str]] = None,
        max_pages: int = 1,
        offline: bool = False,
    ) -> List[NormalizedVacancy]:
        """Execute multi-portal search with error isolation and deduplication.

        Args:
            queries: List of keyword search strings.
            portals: Specific portals to query (defaults to all live portals).
            max_pages: Number of pages to fetch per portal/query.
            offline: If True, bypasses network and uses MockScraper.

        Returns:
            Deduplicated list of NormalizedVacancy instances.
        """
        if not queries:
            queries = ["ingeniero civil"]

        # If offline mode, query only the mock scraper
        if offline:
            mock_scraper = self.scrapers.get("mock") or MockScraper()
            all_mock: List[NormalizedVacancy] = []
            seen_ids: Set[str] = set()
            for q in queries:
                vacs = mock_scraper.search(q, max_pages=max_pages)
                for v in vacs:
                    if v.id not in seen_ids:
                        seen_ids.add(v.id)
                        all_mock.append(v)
            self.last_run_stats = {
                "offline": True,
                "total_scraped": len(all_mock),
                "deduplicated_count": len(all_mock),
                "portal_counts": {"mock": len(all_mock)},
                "failures": {},
            }
            return all_mock

        # Determine target portals
        if portals:
            active_portal_names = [p.strip().lower() for p in portals if p.strip().lower() in self.scrapers]
        else:
            # All live scrapers except mock
            active_portal_names = [name for name in self.scrapers if name != "mock"]

        collected_vacancies: List[NormalizedVacancy] = []
        portal_counts: Dict[str, int] = {p: 0 for p in active_portal_names}
        failures: Dict[str, str] = {}

        for portal_name in active_portal_names:
            scraper = self.scrapers[portal_name]
            for query in queries:
                try:
                    logger.info(f"Executing search on [{portal_name}] for query: '{query}'")
                    results = scraper.search(query=query, max_pages=max_pages)
                    collected_vacancies.extend(results)
                    portal_counts[portal_name] += len(results)
                except Exception as exc:
                    err_msg = f"Portal [{portal_name}] error on query '{query}': {exc}"
                    logger.error(err_msg, exc_info=True)
                    failures[portal_name] = str(exc)
                    # Isolated fault domain: continue with other portals

        # Global deduplication by vacancy.id
        deduplicated: List[NormalizedVacancy] = []
        seen_ids: Set[str] = set()
        for vac in collected_vacancies:
            if vac.id not in seen_ids:
                seen_ids.add(vac.id)
                deduplicated.append(vac)

        self.last_run_stats = {
            "offline": False,
            "total_scraped": len(collected_vacancies),
            "deduplicated_count": len(deduplicated),
            "portal_counts": portal_counts,
            "failures": failures,
        }

        logger.info(
            f"Aggregation complete: {len(collected_vacancies)} scraped, "
            f"{len(deduplicated)} unique vacancies. Failures: {len(failures)}"
        )
        return deduplicated

    def run_profile(
        self,
        profile: ProfileConfig,
        max_pages: int = 1,
        offline: bool = False,
    ) -> List[NormalizedVacancy]:
        """Execute search using parameters defined in a ProfileConfig."""
        queries = profile.search_queries
        if not queries and profile.search_config:
            queries = profile.search_config.query_strings

        portals = None
        if profile.search_config and profile.search_config.portals:
            portals = profile.search_config.portals

        return self.run(
            queries=queries,
            portals=portals,
            max_pages=max_pages,
            offline=offline,
        )
