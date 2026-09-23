"""Modular job scrapers package."""

from job_hunter.scrapers.base import BaseScraper
from job_hunter.scrapers.computrabajo import ComputrabajoScraper
from job_hunter.scrapers.elempleo import ElEmpleoScraper
from job_hunter.scrapers.engine import JobAggregationEngine
from job_hunter.scrapers.linkedin import LinkedInScraper
from job_hunter.scrapers.mock_scraper import MockScraper
from job_hunter.scrapers.remotive import RemotiveScraper

__all__ = [
    "BaseScraper",
    "ComputrabajoScraper",
    "ElEmpleoScraper",
    "LinkedInScraper",
    "RemotiveScraper",
    "MockScraper",
    "JobAggregationEngine",
]
