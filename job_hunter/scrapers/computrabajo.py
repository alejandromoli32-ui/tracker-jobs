"""Computrabajo Colombia scraper with -en-remoto slug filtering and pagination."""

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


class ComputrabajoScraper(BaseScraper):
    """Scraper for Computrabajo Colombia (co.computrabajo.com)."""

    name: str = "computrabajo"
    base_url: str = "https://co.computrabajo.com"

    def __init__(
        self,
        client: Optional[HttpClient] = None,
        fetch_details: bool = False,
    ):
        super().__init__(client=client)
        self.fetch_details = fetch_details

    def _build_search_url(self, query: str, page: int = 1) -> str:
        """Construct Computrabajo search URL with remote filter and pagination."""
        clean_q = re.sub(r"[^a-zA-Z0-9áéíóúÁÉÍÓÚñÑ\s]+", " ", query).strip()
        slug = re.sub(r"\s+", "-", clean_q.lower())

        if slug:
            base = f"{self.base_url}/trabajo-de-{slug}-en-remoto"
        else:
            base = f"{self.base_url}/ofertas-de-trabajo-en-remoto"

        if page > 1:
            return f"{base}?p={page}"
        return base

    def search(self, query: str, max_pages: int = 2) -> List[NormalizedVacancy]:
        """Scrape Computrabajo for the given search query across pages."""
        vacancies: List[NormalizedVacancy] = []

        for page in range(1, max_pages + 1):
            url = self._build_search_url(query, page=page)
            logger.info(f"[Computrabajo] Fetching page {page}: {url}")

            html_text = self.client.get_html(url)
            page_vacancies = self.parse_listings_html(html_text) if html_text else []

            # If slug-based search yields no cards, try standard query search
            if not page_vacancies and page == 1:
                from urllib.parse import quote_plus
                fallback_url = f"{self.base_url}/ofertas-de-trabajo/?q={quote_plus(query.strip())}"
                logger.info(f"[Computrabajo] Slug URL yielded no cards. Trying standard query: {fallback_url}")
                html_text = self.client.get_html(fallback_url)
                if html_text:
                    page_vacancies = self.parse_listings_html(html_text)

            if not page_vacancies:
                logger.info(f"[Computrabajo] No job cards found on page {page}. Halting pagination.")
                break

            vacancies.extend(page_vacancies)

        return vacancies

    def parse_listings_html(self, html_text: str) -> List[NormalizedVacancy]:
        """Parse Computrabajo listing page HTML into NormalizedVacancy objects."""
        soup = BeautifulSoup(html_text, "html.parser")
        cards = soup.select("article.box_offer")
        results: List[NormalizedVacancy] = []

        for card in cards:
            try:
                title_elem = card.select_one("a.js-o-link") or card.select_one("h2 a") or card.select_one("h2")
                if not title_elem:
                    continue

                raw_title = title_elem.get_text(strip=True)
                raw_href = title_elem.get("href", "")
                if not raw_href and card.select_one("a.js-o-link"):
                    raw_href = card.select_one("a.js-o-link").get("href", "")

                if not raw_title or not raw_href:
                    continue

                clean_href = raw_href.split("#")[0].split("?")[0]
                direct_url = urljoin(self.base_url, clean_href)

                # Company extraction (ignoring ratings)
                company_elem = card.select_one("p.fs16 a") or card.select_one("p.fs16")
                raw_company = company_elem.get_text(strip=True) if company_elem else "Confidencial"

                # Location extraction
                loc_elem = card.select_one("p.fs16 span.mr10") or card.select_one("span.mr10")
                if not loc_elem:
                    p_fs16 = card.select("p.fs16")
                    if len(p_fs16) > 1:
                        loc_elem = p_fs16[1]
                raw_location = loc_elem.get_text(strip=True) if loc_elem else "Colombia"

                # Salary extraction
                salary_elem = card.select_one("span.dIB")
                raw_salary = salary_elem.get_text(strip=True) if salary_elem else None

                # Publication date
                date_elem = card.select_one("p.fc_aux")
                raw_date = date_elem.get_text(strip=True) if date_elem else None

                # Snippet / Description
                desc_elem = card.select_one("p.mbB") or card.select_one("div.box_offer_desc")
                raw_snippet = desc_elem.get_text(separator=" ", strip=True) if desc_elem else raw_title

                full_desc = raw_snippet
                if self.fetch_details:
                    detail_text = self.fetch_detail(direct_url)
                    if detail_text:
                        full_desc = detail_text

                card_id = card.get("data-id") or card.get("id") or None

                vacancy = normalize_vacancy(
                    title=raw_title,
                    company=raw_company,
                    direct_url=direct_url,
                    full_description=full_desc,
                    source_portal=self.name,
                    publication_date=raw_date,
                    location=raw_location,
                    modality="remoto",
                    salary_range=raw_salary,
                    raw_snippet=raw_snippet,
                    extra_metadata={"external_id": card_id} if card_id else {},
                )
                results.append(vacancy)

            except Exception as e:
                logger.warning(f"[Computrabajo] Failed to parse card: {e}")
                continue

        return results

    def fetch_detail(self, url: str) -> Optional[str]:
        """Fetch and extract full job description from detail page."""
        html_text = self.client.get_html(url)
        if not html_text:
            return None

        soup = BeautifulSoup(html_text, "html.parser")
        desc_elem = soup.select_one("div.box_detail p.mbB") or soup.select_one("div.box_detail")
        requirements_elem = soup.select_one("div.box_detail ul.disc")

        parts = []
        if desc_elem:
            parts.append(desc_elem.get_text(separator="\n", strip=True))
        if requirements_elem:
            parts.append("Requerimientos:\n" + requirements_elem.get_text(separator="\n", strip=True))

        return "\n\n".join(parts) if parts else None
