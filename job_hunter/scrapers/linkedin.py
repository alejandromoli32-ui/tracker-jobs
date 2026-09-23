"""LinkedIn Jobs public guest feed scraper using remote filter and Colombia geoId."""

from __future__ import annotations

import logging
import re
from typing import List, Optional
from urllib.parse import urlencode, urljoin

from bs4 import BeautifulSoup

from job_hunter.client import HttpClient
from job_hunter.models import NormalizedVacancy
from job_hunter.normalizer import normalize_vacancy
from job_hunter.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class LinkedInScraper(BaseScraper):
    """Scraper for LinkedIn public guest jobs feed."""

    name: str = "linkedin"
    base_url: str = "https://www.linkedin.com"
    search_endpoint: str = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    detail_endpoint: str = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting"

    def __init__(
        self,
        client: Optional[HttpClient] = None,
        fetch_details: bool = False,
    ):
        super().__init__(client=client)
        self.fetch_details = fetch_details

    def _build_search_url(self, query: str, page: int = 1) -> str:
        """Construct LinkedIn guest API search URL."""
        params = {
            "keywords": query.strip(),
            "location": "Colombia",
            "geoId": "100876405",  # Colombia LinkedIn Geo ID
            "f_WT": "2",           # 100% Remote / Teletrabajo
            "start": str((page - 1) * 25),
        }
        return f"{self.search_endpoint}?{urlencode(params)}"

    def search(self, query: str, max_pages: int = 2) -> List[NormalizedVacancy]:
        """Scrape LinkedIn public guest feed for query across pages."""
        vacancies: List[NormalizedVacancy] = []

        for page in range(1, max_pages + 1):
            url = self._build_search_url(query, page=page)
            logger.info(f"[LinkedIn] Fetching page {page} (start={(page - 1) * 25}): {url}")

            html_text = self.client.get_html(url)
            if not html_text:
                logger.warning(f"[LinkedIn] Empty or failed response for page {page}")
                break

            page_vacancies = self.parse_listings_html(html_text)
            if not page_vacancies:
                logger.info(f"[LinkedIn] No job cards found on page {page}. Halting pagination.")
                break

            vacancies.extend(page_vacancies)

        return vacancies

    def parse_listings_html(self, html_text: str) -> List[NormalizedVacancy]:
        """Parse LinkedIn search fragment HTML into NormalizedVacancy objects."""
        soup = BeautifulSoup(html_text, "html.parser")
        items = soup.select("li")
        results: List[NormalizedVacancy] = []

        for item in items:
            try:
                card = item.select_one("div.base-search-card") or item
                title_elem = card.select_one("h3.base-search-card__title") or card.select_one("h3")
                link_elem = card.select_one("a.base-card__full-link") or card.select_one("a")

                if not title_elem or not link_elem:
                    continue

                raw_title = title_elem.get_text(strip=True)
                raw_href = link_elem.get("href", "")
                if not raw_title or not raw_href:
                    continue

                clean_href = raw_href.split("?")[0].split("#")[0]
                direct_url = urljoin(self.base_url, clean_href)

                # Company
                comp_elem = card.select_one("h4.base-search-card__subtitle") or card.select_one("a.hidden-nested-link")
                raw_company = comp_elem.get_text(strip=True) if comp_elem else "Confidencial"

                # Location
                loc_elem = card.select_one("span.job-search-card__location")
                raw_location = loc_elem.get_text(strip=True) if loc_elem else "Colombia"

                # Date
                time_elem = card.select_one("time")
                raw_date = None
                if time_elem:
                    raw_date = time_elem.get("datetime") or time_elem.get_text(strip=True)

                raw_snippet = raw_title
                full_desc = raw_title

                # Job ID from URL suffix e.g. -(\d+)\??
                job_id_match = re.search(r"-(\d+)(?:\?|$)", direct_url)
                job_id = job_id_match.group(1) if job_id_match else None

                if self.fetch_details and job_id:
                    detail_text = self.fetch_detail(job_id)
                    if detail_text:
                        full_desc = detail_text

                vacancy = normalize_vacancy(
                    title=raw_title,
                    company=raw_company,
                    direct_url=direct_url,
                    full_description=full_desc,
                    source_portal=self.name,
                    publication_date=raw_date,
                    location=raw_location,
                    modality="remoto",
                    salary_range=None,
                    raw_snippet=raw_snippet,
                    extra_metadata={"external_id": job_id} if job_id else {},
                )
                results.append(vacancy)

            except Exception as e:
                logger.warning(f"[LinkedIn] Failed to parse card: {e}")
                continue

        return results

    def fetch_detail(self, job_id: str) -> Optional[str]:
        """Fetch job description from LinkedIn guest detail endpoint."""
        url = f"{self.detail_endpoint}/{job_id}"
        html_text = self.client.get_html(url)
        if not html_text:
            return None

        soup = BeautifulSoup(html_text, "html.parser")
        desc_elem = soup.select_one("div.description__text") or soup.select_one("div.show-more-less-html__markup")
        if desc_elem:
            return desc_elem.get_text(separator="\n", strip=True)
        return None
