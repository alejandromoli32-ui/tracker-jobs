"""ElEmpleo Colombia scraper with search query, pagination, and selector extraction."""

from __future__ import annotations

import logging
import re
from typing import List, Optional
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup

from job_hunter.client import HttpClient
from job_hunter.models import NormalizedVacancy
from job_hunter.normalizer import normalize_vacancy
from job_hunter.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class ElEmpleoScraper(BaseScraper):
    """Scraper for ElEmpleo Colombia (www.elempleo.com/co)."""

    name: str = "elempleo"
    base_url: str = "https://www.elempleo.com"

    def __init__(
        self,
        client: Optional[HttpClient] = None,
        fetch_details: bool = False,
    ):
        super().__init__(client=client)
        self.fetch_details = fetch_details

    def _build_search_url(self, query: str, page: int = 1) -> str:
        """Construct ElEmpleo search URL with query and pagination."""
        encoded_query = quote_plus(query.strip())
        url = f"{self.base_url}/co/ofertas-empleo?trabajo={encoded_query}"
        if page > 1:
            url += f"&pagina={page}"
        return url

    def search(self, query: str, max_pages: int = 2) -> List[NormalizedVacancy]:
        """Scrape ElEmpleo for the given query across pages."""
        vacancies: List[NormalizedVacancy] = []

        for page in range(1, max_pages + 1):
            url = self._build_search_url(query, page=page)
            logger.info(f"[ElEmpleo] Fetching page {page}: {url}")

            html_text = self.client.get_html(url)
            if not html_text:
                logger.warning(f"[ElEmpleo] Empty or failed response for page {page}")
                break

            page_vacancies = self.parse_listings_html(html_text)
            if not page_vacancies:
                logger.info(f"[ElEmpleo] No job cards found on page {page}. Halting pagination.")
                break

            vacancies.extend(page_vacancies)

        return vacancies

    def parse_listings_html(self, html_text: str) -> List[NormalizedVacancy]:
        """Parse ElEmpleo listing page HTML into NormalizedVacancy objects."""
        soup = BeautifulSoup(html_text, "html.parser")
        cards = soup.select("div.result-item") or soup.select("div.item-job")
        results: List[NormalizedVacancy] = []

        for card in cards:
            try:
                title_elem = card.select_one("a.js-offer-title") or card.select_one("a.item-title")
                if not title_elem:
                    continue

                raw_title = title_elem.get_text(strip=True)
                raw_href = title_elem.get("href", "")
                if not raw_title or not raw_href:
                    continue

                clean_href = raw_href.split("?")[0].split("#")[0]
                direct_url = urljoin(self.base_url, clean_href)

                # Company
                comp_elem = card.select_one("span.js-offer-company") or card.select_one("span.company-title")
                raw_company = comp_elem.get_text(strip=True) if comp_elem else "Confidencial"

                # City
                city_elem = card.select_one("span.js-offer-city") or card.select_one("span.city")
                raw_city = city_elem.get_text(strip=True) if city_elem else "Colombia"

                # Date
                date_elem = card.select_one("span.js-offer-date") or card.select_one("span.date")
                raw_date = date_elem.get_text(strip=True) if date_elem else None

                # Salary
                salary_elem = card.select_one("span.js-offer-salary") or card.select_one("span.salary")
                raw_salary = salary_elem.get_text(strip=True) if salary_elem else None

                # Description snippet
                desc_elem = card.select_one("div.description-block") or card.select_one("p.text-description")
                raw_snippet = desc_elem.get_text(separator=" ", strip=True) if desc_elem else raw_title

                full_desc = raw_snippet
                if self.fetch_details:
                    detail_text = self.fetch_detail(direct_url)
                    if detail_text:
                        full_desc = detail_text

                # Extract external id from URL suffix -(\d+)$
                external_id = None
                id_match = re.search(r"-(\d+)$", direct_url)
                if id_match:
                    external_id = id_match.group(1)

                vacancy = normalize_vacancy(
                    title=raw_title,
                    company=raw_company,
                    direct_url=direct_url,
                    full_description=full_desc,
                    source_portal=self.name,
                    publication_date=raw_date,
                    location=raw_city,
                    modality="remoto",
                    salary_range=raw_salary,
                    raw_snippet=raw_snippet,
                    extra_metadata={"external_id": external_id} if external_id else {},
                )
                results.append(vacancy)

            except Exception as e:
                logger.warning(f"[ElEmpleo] Failed to parse card: {e}")
                continue

        return results

    def fetch_detail(self, url: str) -> Optional[str]:
        """Fetch and extract description from ElEmpleo detail page."""
        html_text = self.client.get_html(url)
        if not html_text:
            return None

        soup = BeautifulSoup(html_text, "html.parser")
        desc_block = soup.select_one("div.description-block") or soup.select_one("div.e-container-keywords")
        if desc_block:
            return desc_block.get_text(separator="\n", strip=True)
        return None
