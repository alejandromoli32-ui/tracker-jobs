"""Comprehensive test suite for Job Board Scraping & Aggregation Engine (Milestone M2).

Covers:
- Resilient HttpClient (headers, UA rotation, rate limiting, retries, backoff, 429, circuit breaker)
- Normalizer (text, title, company, URL, salary, description cleaning, 16-hex dedup hashing, modality classification)
- Modular scrapers (Computrabajo, ElEmpleo, LinkedIn, Remotive, MockScraper) with HTML/JSON fixtures
- JobAggregationEngine (multi-portal search, error isolation, deduplication, profile execution)
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from job_hunter.client import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    HttpClient,
    HttpClientError,
    HttpRequestError,
    USER_AGENT_POOL,
)
from job_hunter.config import load_profile
from job_hunter.models import NormalizedVacancy, ProfileConfig
from job_hunter.normalizer import (
    clean_company,
    clean_description,
    clean_salary,
    clean_text,
    clean_title,
    clean_url,
    classify_modality,
    compute_dedup_id,
    normalize_vacancy,
)
from job_hunter.scrapers.computrabajo import ComputrabajoScraper
from job_hunter.scrapers.elempleo import ElEmpleoScraper
from job_hunter.scrapers.engine import JobAggregationEngine
from job_hunter.scrapers.linkedin import LinkedInScraper
from job_hunter.scrapers.mock_scraper import MockScraper
from job_hunter.scrapers.remotive import RemotiveScraper

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "job_hunter" / "fixtures"
MOCK_FIXTURES_FILE = FIXTURES_DIR / "mock_vacancies.json"


# =============================================================================
# 1. HttpClient Tests
# =============================================================================

class TestHttpClient:
    """Unit and resilience tests for HttpClient."""

    def test_default_headers_and_user_agent_rotation(self):
        client = HttpClient(rate_limit_delay=0)
        h1 = client._build_headers()
        h2 = client._build_headers()

        assert "User-Agent" in h1
        assert "Accept-Language" in h1
        assert "es-CO" in h1["Accept-Language"]
        assert h1["User-Agent"] in USER_AGENT_POOL
        assert h2["User-Agent"] in USER_AGENT_POOL

    def test_rate_limiting_delay(self):
        client = HttpClient(rate_limit_delay=0.1, jitter_min=0.01, jitter_max=0.02)
        start = time.time()
        client._throttle("test.host.com")
        client._throttle("test.host.com")
        duration = time.time() - start
        assert duration >= 0.1, f"Expected delay >= 0.1s, got {duration:.4f}s"

    def test_rate_limiting_disabled_when_zero(self):
        client = HttpClient(rate_limit_delay=0)
        start = time.time()
        for _ in range(5):
            client._throttle("test.host.com")
        assert (time.time() - start) < 0.1

    def test_retry_on_500_503_eventual_success(self, monkeypatch):
        client = HttpClient(rate_limit_delay=0, max_retries=3)
        calls = 0

        def mock_get(url, **kwargs):
            nonlocal calls
            calls += 1
            resp = requests.Response()
            if calls < 3:
                resp.status_code = 503
            else:
                resp.status_code = 200
                resp._content = b"<html>Success</html>"
            return resp

        monkeypatch.setattr(client.session, "get", mock_get)
        monkeypatch.setattr(time, "sleep", lambda s: None)  # fast-forward sleep

        resp = client.get("https://test.com/api")
        assert resp.status_code == 200
        assert calls == 3
        assert client.circuit_breaker.is_open("test.com") is False

    def test_retry_exhaustion_raises_http_request_error(self, monkeypatch):
        client = HttpClient(rate_limit_delay=0, max_retries=2, circuit_threshold=10)

        def mock_get(url, **kwargs):
            resp = requests.Response()
            resp.status_code = 500
            return resp

        monkeypatch.setattr(client.session, "get", mock_get)
        monkeypatch.setattr(time, "sleep", lambda s: None)

        with pytest.raises(HttpRequestError) as exc_info:
            client.get("https://failing-domain.com/jobs")
        assert "after 3 attempts" in str(exc_info.value)

    def test_rate_limit_429_parses_retry_after(self, monkeypatch):
        client = HttpClient(rate_limit_delay=0, max_retries=2)
        sleeps = []

        def mock_sleep(s):
            sleeps.append(s)

        calls = 0

        def mock_get(url, **kwargs):
            nonlocal calls
            calls += 1
            resp = requests.Response()
            if calls == 1:
                resp.status_code = 429
                resp.headers["Retry-After"] = "5"
            else:
                resp.status_code = 200
                resp._content = b"OK"
            return resp

        monkeypatch.setattr(client.session, "get", mock_get)
        monkeypatch.setattr(time, "sleep", mock_sleep)

        resp = client.get("https://rate-limited.com/search")
        assert resp.status_code == 200
        assert 5.0 in sleeps

    def test_network_timeout_retries_and_recovers(self, monkeypatch):
        client = HttpClient(rate_limit_delay=0, max_retries=2)
        attempts = 0

        def mock_get(url, **kwargs):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise requests.exceptions.Timeout("Read timed out")
            resp = requests.Response()
            resp.status_code = 200
            resp._content = b"Recovered"
            return resp

        monkeypatch.setattr(client.session, "get", mock_get)
        monkeypatch.setattr(time, "sleep", lambda s: None)

        resp = client.get("https://timeout-test.com")
        assert resp.status_code == 200
        assert attempts == 2

    def test_circuit_breaker_trips_after_threshold(self, monkeypatch):
        cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=10.0)
        host = "flaky-portal.com"

        assert cb.is_open(host) is False
        cb.record_failure(host)
        assert cb.is_open(host) is False
        cb.record_failure(host)
        assert cb.is_open(host) is False
        cb.record_failure(host)
        # Threshold reached -> circuit trips
        assert cb.is_open(host) is True

        # In HttpClient, open circuit raises CircuitBreakerOpenError immediately
        client = HttpClient(rate_limit_delay=0)
        client.circuit_breaker = cb
        with pytest.raises(CircuitBreakerOpenError):
            client.get(f"https://{host}/path")

        # After cooldown reset, circuit closes
        cb.reset(host)
        assert cb.is_open(host) is False

    def test_get_html_and_get_json_helpers(self, monkeypatch):
        client = HttpClient(rate_limit_delay=0)

        # Successful HTML
        resp_html = requests.Response()
        resp_html.status_code = 200
        resp_html._content = "<h1>Título</h1>".encode("utf-8")

        # Successful JSON
        resp_json = requests.Response()
        resp_json.status_code = 200
        resp_json._content = json.dumps({"jobs": [1, 2]}).encode("utf-8")

        def mock_get(url, **kwargs):
            if "html" in url:
                return resp_html
            if "json" in url:
                return resp_json
            err = requests.Response()
            err.status_code = 404
            return err

        monkeypatch.setattr(client.session, "get", mock_get)

        assert client.get_html("https://site.com/html") == "<h1>Título</h1>"
        assert client.get_json("https://site.com/json") == {"jobs": [1, 2]}
        assert client.get_html("https://site.com/missing") is None


# =============================================================================
# 2. Normalizer & Hashing Tests
# =============================================================================

class TestNormalizer:
    """Unit tests for string cleaning, deduplication hashing, and modality classification."""

    def test_clean_text_strips_scripts_tags_and_entities(self):
        raw = "   <script>alert(1);</script> Ingeniero&nbsp;Civil &amp; V&iacute;as  <style>body{}</style>  "
        cleaned = clean_text(raw)
        assert cleaned == "Ingeniero Civil & Vías"

    def test_clean_title_removes_badge_tags(self):
        raw1 = "[Remoto] Ingeniera Civil Senior Especialista en Vías (Postulado)"
        assert clean_title(raw1) == "Ingeniera Civil Senior Especialista en Vías"

        raw2 = "  Oferta destacada Directora de Interventoría  "
        assert clean_title(raw2) == "Directora de Interventoría"

        assert clean_title("") == "Vacante Sin Título"
        assert clean_title(None) == "Vacante Sin Título"

    def test_clean_company_removes_ratings_and_defaults(self):
        assert clean_company("4,8 Vías Andinas S.A.S.") == "Vías Andinas S.A.S."
        assert clean_company("3.5 Consorcio Vial") == "Consorcio Vial"
        assert clean_company("Empresa confidencial") == "Confidencial"
        assert clean_company("Importante empresa del sector") == "Importante empresa del sector"
        assert clean_company(None) == "Confidencial"
        assert clean_company("") == "Confidencial"

    def test_clean_url_strips_tracking_parameters(self):
        raw_url = (
            "https://co.computrabajo.com/ofertas-de-trabajo/oferta-12345"
            "?utm_source=linkedin&utm_medium=cpc&position=3&pageNum=1&refId=abc&search=civil#top"
        )
        cleaned = clean_url(raw_url)
        assert cleaned == "https://co.computrabajo.com/ofertas-de-trabajo/oferta-12345?search=civil"
        assert "utm_" not in cleaned
        assert "position" not in cleaned
        assert "#top" not in cleaned

    def test_clean_salary(self):
        assert clean_salary("$ 12.000.000 - $ 15.000.000 COP") == "$ 12.000.000 - $ 15.000.000 COP"
        assert clean_salary("A convenir") is None
        assert clean_salary("No especificado") is None
        assert clean_salary("") is None
        assert clean_salary(None) is None

    def test_clean_description_preserves_structure_strips_scripts(self):
        html_desc = """
        <p>Buscamos <b>Ingeniera Civil</b> para coordinaci&oacute;n remota.</p>
        <script>badCode();</script>
        <ul>
            <li>15 a&ntilde;os de experiencia</li>
            <li>Licencia SST vigente</li>
        </ul>
        <br>
        Enviar hoja de vida.
        """
        desc = clean_description(html_desc)
        assert "badCode" not in desc
        assert "Buscamos Ingeniera Civil para coordinación remota." in desc
        assert "• 15 años de experiencia" in desc
        assert "• Licencia SST vigente" in desc
        assert "Enviar hoja de vida." in desc

    def test_deterministic_dedup_id_16_hex(self):
        id1 = compute_dedup_id(
            "Ingeniera Civil Vías",
            "Vías Andinas S.A.S.",
            "https://co.computrabajo.com/oferta/100?utm_source=test",
        )
        id2 = compute_dedup_id(
            "   ingeniera  civil vías ",
            "4.8 Vías Andinas S.A.S.",
            "https://co.computrabajo.com/oferta/100#fragment",
        )
        assert len(id1) == 16
        assert re.match(r"^[0-9a-f]{16}$", id1)
        # Because titles, companies, and canonical URLs match, IDs must be identical
        assert id1 == id2

        # A different title yields a distinct hash
        id3 = compute_dedup_id(
            "Ingeniero Estructural",
            "Vías Andinas S.A.S.",
            "https://co.computrabajo.com/oferta/100",
        )
        assert id1 != id3

    @pytest.mark.parametrize(
        "text,declared,expected",
        [
            ("Residente de obra en campamento frente de obra túneles", None, "presencial"),
            ("Jefe de patio y maquinaria pesada en cantera", None, "presencial"),
            ("Inspector SST en planta industrial turnos rotativos en sitio", None, "presencial"),
            ("Abstenerse personas interesadas en trabajo remoto", None, "presencial"),
            ("Esquema mixto 3 días en oficina y 2 en casa", None, "hibrido"),
            ("Modalidad híbrido con alternancia", None, "hibrido"),
            ("Consultoría técnica 100% teletrabajo / virtual", None, "remoto"),
            ("Home office nacional para coordinación de proyectos", None, "remoto"),
            ("Ingeniero de diseño vial remoto Colombia", None, "remoto"),
            ("Profesional de ingeniería civil con COPNIA", None, "desconocido"),
            ("Ingeniero civil", "presencial", "presencial"),
            ("Ingeniero civil", "remoto", "remoto"),
            ("Ingeniero civil", "hibrido", "hibrido"),
        ],
    )
    def test_classify_modality(self, text, declared, expected):
        assert classify_modality(text, declared) == expected

    def test_normalize_vacancy_full_factory(self):
        vac = normalize_vacancy(
            title="[Remoto] Coordinadora Vial & SST",
            company="4,5 Vías del Norte S.A.S.",
            direct_url="https://co.computrabajo.com/oferta/789?utm_medium=email#apply",
            full_description="<p>Coordinación 100% virtual de contratos viales y SG-SST.</p>",
            source_portal="computrabajo",
            publication_date="2026-09-20",
            location="Bogotá (Remoto)",
            modality=None,
            salary_range="$ 10.000.000 COP",
            raw_snippet="Coordinación 100% virtual",
        )
        assert isinstance(vac, NormalizedVacancy)
        assert len(vac.id) == 16
        assert vac.title == "Coordinadora Vial & SST"
        assert vac.company == "Vías del Norte S.A.S."
        assert vac.direct_url == "https://co.computrabajo.com/oferta/789"
        assert vac.modality == "remoto"
        assert vac.salary_range == "$ 10.000.000 COP"
        assert vac.source_portal == "computrabajo"


# =============================================================================
# 3. Modular Portal Scrapers Tests
# =============================================================================

class TestComputrabajoScraper:
    """Tests for ComputrabajoScraper."""

    SAMPLE_HTML = """
    <html>
      <body>
        <div class="box_offers">
          <article class="box_offer" data-id="19581264D419957161373E686DCF3405" id="offer_1">
            <h2><a class="js-o-link" href="/ofertas-de-trabajo/oferta-de-trabajo-de-ingeniero-civil-vias-12345">Ingeniero Civil Vías e Infraestructura</a></h2>
            <p class="fs16"><a href="/empresa-1">4,8 Constructora Coninvial S.A.S.</a> <span class="mr10">Bogotá, D.C.</span></p>
            <p class="mbB">Importante empresa requiere Ingeniero Civil con 10 años de experiencia en vías y pavimentos...</p>
            <span class="dIB"><span class="icon i_salary"></span>$ 8.000.000,00 (Mensual)</span>
            <p class="fc_aux">Hace 2 días</p>
          </article>
          <article class="box_offer" data-id="BAD_CARD">
            <!-- Missing title link -->
            <p>Malformed card</p>
          </article>
        </div>
      </body>
    </html>
    """

    def test_parse_listings_html(self):
        client = HttpClient(rate_limit_delay=0)
        scraper = ComputrabajoScraper(client=client)
        vacancies = scraper.parse_listings_html(self.SAMPLE_HTML)

        assert len(vacancies) == 1
        vac = vacancies[0]
        assert vac.title == "Ingeniero Civil Vías e Infraestructura"
        assert vac.company == "Constructora Coninvial S.A.S."
        assert vac.direct_url == "https://co.computrabajo.com/ofertas-de-trabajo/oferta-de-trabajo-de-ingeniero-civil-vias-12345"
        assert vac.location == "Bogotá, D.C."
        assert "$ 8.000.000,00 (Mensual)" in vac.salary_range
        assert vac.source_portal == "computrabajo"
        assert vac.extra_metadata.get("external_id") == "19581264D419957161373E686DCF3405"

    def test_search_pagination_and_network_mock(self, monkeypatch):
        client = HttpClient(rate_limit_delay=0)
        scraper = ComputrabajoScraper(client=client)

        page_calls = []

        def mock_get_html(url, params=None):
            page_calls.append(url)
            if len(page_calls) == 1:
                return self.SAMPLE_HTML
            return "<html><body>No more offers</body></html>"

        monkeypatch.setattr(client, "get_html", mock_get_html)

        results = scraper.search(query="ingeniero civil vias", max_pages=2)
        assert len(results) == 1
        assert len(page_calls) == 2
        assert "trabajo-de-ingeniero-civil-vias-en-remoto" in page_calls[0]
        assert "?p=2" in page_calls[1]


class TestElEmpleoScraper:
    """Tests for ElEmpleoScraper."""

    SAMPLE_HTML = """
    <html>
      <body>
        <div class="js-result-list">
          <div class="result-item">
            <h2 class="item-title">
              <a class="js-offer-title" href="/co/ofertas-trabajo/director-interventoria-vial-1886700053">Director de Interventoría Vial</a>
            </h2>
            <span class="js-offer-company">KMA CONSTRUCCIONES S.A.S.</span>
            <span class="js-offer-city">Medellín</span>
            <span class="js-offer-date">Hoy</span>
            <span class="js-offer-salary">$ 12.000.000</span>
            <div class="description-block">Buscamos Director para supervisión de obras viales con 15 años de experiencia.</div>
          </div>
        </div>
      </body>
    </html>
    """

    def test_parse_listings_html(self):
        client = HttpClient(rate_limit_delay=0)
        scraper = ElEmpleoScraper(client=client)
        vacancies = scraper.parse_listings_html(self.SAMPLE_HTML)

        assert len(vacancies) == 1
        vac = vacancies[0]
        assert vac.title == "Director de Interventoría Vial"
        assert vac.company == "KMA CONSTRUCCIONES S.A.S."
        assert vac.direct_url == "https://www.elempleo.com/co/ofertas-trabajo/director-interventoria-vial-1886700053"
        assert vac.location == "Medellín"
        assert vac.source_portal == "elempleo"
        assert vac.extra_metadata.get("external_id") == "1886700053"


class TestLinkedInScraper:
    """Tests for LinkedInScraper."""

    SAMPLE_HTML = """
    <ul>
      <li>
        <div class="base-search-card">
          <h3 class="base-search-card__title">Coordinador SST y Gestión Ambiental Remoto</h3>
          <a class="base-card__full-link" href="https://co.linkedin.com/jobs/view/coordinador-sst-4461715824?position=1&pageNum=0">Ver oferta</a>
          <h4 class="base-search-card__subtitle">HMV Ingenieros</h4>
          <span class="job-search-card__location">Bogotá, Colombia</span>
          <time datetime="2026-09-18">Hace 3 días</time>
        </div>
      </li>
    </ul>
    """

    def test_parse_listings_html(self):
        client = HttpClient(rate_limit_delay=0)
        scraper = LinkedInScraper(client=client)
        vacancies = scraper.parse_listings_html(self.SAMPLE_HTML)

        assert len(vacancies) == 1
        vac = vacancies[0]
        assert vac.title == "Coordinador SST y Gestión Ambiental Remoto"
        assert vac.company == "HMV Ingenieros"
        assert vac.direct_url == "https://co.linkedin.com/jobs/view/coordinador-sst-4461715824"
        assert vac.location == "Bogotá, Colombia"
        assert vac.publication_date == "2026-09-18"
        assert vac.source_portal == "linkedin"
        assert vac.modality == "remoto"
        assert vac.extra_metadata.get("external_id") == "4461715824"


class TestRemotiveScraper:
    """Tests for RemotiveScraper."""

    SAMPLE_JSON = {
        "job-count": 1,
        "jobs": [
            {
                "id": 2091141,
                "url": "https://remotive.com/remote-jobs/all-other/infrastructure-consultant-2091141",
                "title": "Senior Infrastructure & Safety Consultant",
                "company_name": "Global Tech Infra",
                "category": "all-other",
                "tags": ["infrastructure", "safety", "consulting"],
                "publication_date": "2026-09-18T10:00:00",
                "candidate_required_location": "Worldwide",
                "salary": "$80,000 - $100,000 USD",
                "description": "<p>We are seeking a senior consultant for transport infrastructure safety...</p>",
            }
        ],
    }

    def test_parse_api_response(self):
        client = HttpClient(rate_limit_delay=0)
        scraper = RemotiveScraper(client=client)
        vacancies = scraper.parse_api_response(self.SAMPLE_JSON)

        assert len(vacancies) == 1
        vac = vacancies[0]
        assert vac.title == "Senior Infrastructure & Safety Consultant"
        assert vac.company == "Global Tech Infra"
        assert vac.direct_url == "https://remotive.com/remote-jobs/all-other/infrastructure-consultant-2091141"
        assert vac.location == "Worldwide"
        assert vac.source_portal == "remotive"
        assert vac.modality == "remoto"
        assert vac.extra_metadata.get("external_id") == "2091141"


class TestMockScraper:
    """Tests for MockScraper offline fixture dataset."""

    def test_loads_all_11_fixtures(self):
        assert MOCK_FIXTURES_FILE.exists(), f"Missing fixture file: {MOCK_FIXTURES_FILE}"
        scraper = MockScraper(fixture_path=MOCK_FIXTURES_FILE)
        vacancies = scraper.search("*")
        assert len(vacancies) == 11

    def test_keyword_filtering_accent_insensitive(self):
        scraper = MockScraper(fixture_path=MOCK_FIXTURES_FILE)

        # Unaccented search "vias" matches both "vías" and "Vías"
        vias_vacs = scraper.search("vias")
        assert len(vias_vacs) >= 4
        for v in vias_vacs:
            combined = f"{v.title} {v.full_description}".lower()
            assert "via" in combined or "vía" in combined

        # Search "sst" matches SST positions
        sst_vacs = scraper.search("sst")
        assert len(sst_vacs) >= 4

        # Search for non-existent term falls back safely to full set
        fallback_vacs = scraper.search("palabra_inexistente_xyz_123")
        assert len(fallback_vacs) == 11


# =============================================================================
# 4. JobAggregationEngine Tests
# =============================================================================

class TestJobAggregationEngine:
    """Integration and error tolerance tests for JobAggregationEngine."""

    def test_offline_mode_returns_mock_vacancies(self):
        engine = JobAggregationEngine()
        vacancies = engine.run(queries=["vias", "sst"], offline=True)
        assert len(vacancies) > 0
        assert engine.last_run_stats["offline"] is True
        assert engine.last_run_stats["deduplicated_count"] == len(vacancies)

    def test_multi_portal_orchestration_mocked(self):
        # Create mock scrapers returning predefined vacancies
        scraper1 = MagicMock()
        vac1 = normalize_vacancy("Job 1", "Co 1", "https://portal1.com/1", "Desc 1", "portal1")
        scraper1.search.return_value = [vac1]

        scraper2 = MagicMock()
        vac2 = normalize_vacancy("Job 2", "Co 2", "https://portal2.com/2", "Desc 2", "portal2")
        scraper2.search.return_value = [vac2]

        custom_scrapers = {"portal1": scraper1, "portal2": scraper2}
        engine = JobAggregationEngine(custom_scrapers=custom_scrapers)

        results = engine.run(queries=["query1"], portals=["portal1", "portal2"])
        assert len(results) == 2
        assert {v.source_portal for v in results} == {"portal1", "portal2"}
        assert scraper1.search.called
        assert scraper2.search.called

    def test_error_isolation_single_portal_failure_does_not_abort_run(self):
        """When Portal A raises a fatal network or parsing error, Portal B succeeds."""
        failing_scraper = MagicMock()
        failing_scraper.search.side_effect = RuntimeError("Fatal connection reset by peer")

        working_scraper = MagicMock()
        working_vac = normalize_vacancy("Surviving Job", "Co", "https://ok.com/job", "Desc", "working_portal")
        working_scraper.search.return_value = [working_vac]

        engine = JobAggregationEngine(
            custom_scrapers={"failing": failing_scraper, "working": working_scraper}
        )

        results = engine.run(queries=["civil"], portals=["failing", "working"])

        # Engine must not raise RuntimeError, and must return working portal results
        assert len(results) == 1
        assert results[0].title == "Surviving Job"
        assert "failing" in engine.last_run_stats["failures"]
        assert "Fatal connection reset" in engine.last_run_stats["failures"]["failing"]

    def test_global_deduplication_across_queries_and_portals(self):
        """Vacancies with identical canonical title, company, and URL are deduplicated."""
        vac_a = normalize_vacancy(
            "Ingeniero de Pavimentos",
            "Consorcio Vial",
            "https://portal.com/job/100?utm_source=a",
            "Desc",
            "portal1",
        )
        vac_b = normalize_vacancy(
            "  ingeniero de pavimentos ",
            "4.8 Consorcio Vial",
            "https://portal.com/job/100#apply",
            "Desc",
            "portal2",
        )
        assert vac_a.id == vac_b.id

        mock_scraper = MagicMock()
        mock_scraper.search.return_value = [vac_a, vac_b]

        engine = JobAggregationEngine(custom_scrapers={"test": mock_scraper})
        results = engine.run(queries=["vias"], portals=["test"])

        assert len(results) == 1
        assert engine.last_run_stats["total_scraped"] == 2
        assert engine.last_run_stats["deduplicated_count"] == 1

    def test_run_profile_integration(self):
        """Execute engine against Profile 1 declarative configuration."""
        profile = load_profile("profile_1_civil_vias_sst")
        assert isinstance(profile, ProfileConfig)

        engine = JobAggregationEngine()
        results = engine.run_profile(profile, offline=True)
        assert len(results) > 0
        assert all(isinstance(v, NormalizedVacancy) for v in results)
