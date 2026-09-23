"""Adversarial stress and edge-case test suite for Milestone M2.

Covers:
- Client network resilience under 429 floods, absurd Retry-After headers, and connection timeouts
- Circuit breaker lifecycle, half-open transitions, and short-circuit verification
- Malformed HTML/JSON, binary garbage, and null-byte robustness
- Deduplication hashing invariance across whitespace, casing, UI badges, and tracking params
- Modality classifier safety precedence (obra/campamento overriding remote terms)
- Scraper parsing tolerance on minimalist or broken DOM fragments
- JobAggregationEngine error isolation under cascading scraper crashes and total portal outages
"""

from __future__ import annotations

import json
import re
import time
from unittest.mock import MagicMock

import pytest
import requests

from job_hunter.client import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    HttpClient,
    HttpClientError,
    HttpRequestError,
)
from job_hunter.models import NormalizedVacancy
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
from job_hunter.scrapers.base import BaseScraper
from job_hunter.scrapers.computrabajo import ComputrabajoScraper
from job_hunter.scrapers.elempleo import ElEmpleoScraper
from job_hunter.scrapers.engine import JobAggregationEngine
from job_hunter.scrapers.linkedin import LinkedInScraper
from job_hunter.scrapers.remotive import RemotiveScraper


# =============================================================================
# 1. HttpClient Adversarial & Network Failure Challenges
# =============================================================================

class TestHttpClientAdversarial:
    """Stress testing network failure modes, absurd headers, and circuit breaker."""

    def test_adversarial_429_absurd_retry_after_headers(self):
        client = HttpClient(rate_limit_delay=0)

        # 1. Negative Retry-After
        resp_neg = requests.Response()
        resp_neg.status_code = 429
        resp_neg.headers["Retry-After"] = "-50"
        backoff_neg = client._calculate_backoff(0, resp_neg)
        assert backoff_neg >= 1.0

        # 2. Non-numeric HTTP-date string
        resp_date = requests.Response()
        resp_date.status_code = 429
        resp_date.headers["Retry-After"] = "Wed, 21 Oct 2026 07:28:00 GMT"
        backoff_date = client._calculate_backoff(0, resp_date)
        assert backoff_date > 0.0

        # 3. Huge numeric Retry-After capped at 30 seconds
        resp_huge = requests.Response()
        resp_huge.status_code = 429
        resp_huge.headers["Retry-After"] = "99999999"
        backoff_huge = client._calculate_backoff(0, resp_huge)
        assert backoff_huge == 30.0

        # 4. Zero Retry-After handled gracefully
        resp_zero = requests.Response()
        resp_zero.status_code = 429
        resp_zero.headers["Retry-After"] = "0"
        backoff_zero = client._calculate_backoff(0, resp_zero)
        assert backoff_zero == 1.0

    def test_adversarial_429_persistent_flood_exhaustion(self, monkeypatch):
        client = HttpClient(rate_limit_delay=0, max_retries=3, circuit_threshold=5)
        calls = 0

        def mock_flood(url, **kwargs):
            nonlocal calls
            calls += 1
            r = requests.Response()
            r.status_code = 429
            r.headers["Retry-After"] = "0.01"
            return r

        monkeypatch.setattr(client.session, "get", mock_flood)
        monkeypatch.setattr(time, "sleep", lambda s: None)

        with pytest.raises(HttpRequestError) as exc_info:
            client.get("https://rate-limit-flood.com/api")

        assert calls == 4  # 1 initial + 3 retries
        assert "after 4 attempts" in str(exc_info.value)
        assert client.circuit_breaker._failures.get("rate-limit-flood.com") == 1

    def test_adversarial_connection_and_ssl_timeouts(self, monkeypatch):
        client = HttpClient(rate_limit_delay=0, max_retries=2, circuit_threshold=2)
        attempts = 0

        def mock_error(url, **kwargs):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise requests.exceptions.ConnectTimeout("Connect timeout 10000ms")
            elif attempts == 2:
                raise requests.exceptions.SSLError("SSL Handshake failed")
            raise requests.exceptions.ConnectionError("Connection aborted by peer")

        monkeypatch.setattr(client.session, "get", mock_error)
        monkeypatch.setattr(time, "sleep", lambda s: None)

        with pytest.raises(HttpRequestError) as exc_info:
            client.get("https://unstable-portal.org/jobs")

        assert attempts == 3  # initial + 2 retries
        assert "after 3 attempts" in str(exc_info.value)
        # Breaker failure counter incremented
        assert client.circuit_breaker._failures.get("unstable-portal.org") == 1

    def test_adversarial_circuit_breaker_short_circuit_and_cooldown_reset(self):
        cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=0.04)
        host = "flaky-host.com"

        assert cb.is_open(host) is False
        cb.record_failure(host)
        assert cb.is_open(host) is False
        cb.record_failure(host)
        # Breaker trips
        assert cb.is_open(host) is True

        # When breaker is open, HttpClient must raise CircuitBreakerOpenError without hitting network
        client = HttpClient(rate_limit_delay=0)
        client.circuit_breaker = cb
        mock_net = MagicMock()
        client.session.get = mock_net

        with pytest.raises(CircuitBreakerOpenError) as exc_info:
            client.get(f"https://{host}/search")

        assert "Circuit breaker is open" in str(exc_info.value)
        assert not mock_net.called

        # Wait for cooldown to expire
        time.sleep(0.05)
        # Breaker half-open reset
        assert cb.is_open(host) is False
        assert cb._failures.get(host) == 0

    def test_adversarial_malformed_html_and_null_bytes(self):
        client = HttpClient(rate_limit_delay=0)
        garbage_samples = [
            "",
            "   \t\n   ",
            "\x00\x00\x01\xfe\xff",
            "<div class='box_offer'>" * 500 + "Unclosed soup" + "</div>" * 200,
            "&amp;&lt;&gt;&#9999999;&badentity;;",
            "%PDF-1.4\n1 0 obj\n<<>>\nendobj",
        ]

        computrabajo = ComputrabajoScraper(client=client)
        elempleo = ElEmpleoScraper(client=client)
        linkedin = LinkedInScraper(client=client)

        for sample in garbage_samples:
            assert computrabajo.parse_listings_html(sample) == []
            assert elempleo.parse_listings_html(sample) == []
            assert linkedin.parse_listings_html(sample) == []

    def test_adversarial_remotive_malformed_json_payloads(self):
        client = HttpClient(rate_limit_delay=0)
        remotive = RemotiveScraper(client=client)

        corrupted_payloads = [
            {},
            {"job-count": 0},
            {"jobs": None},
            {"jobs": "this should be a list"},
            {"jobs": [None, 123, "invalid", {}, {"title": None}]},
            {
                "jobs": [
                    {
                        "id": 9999,
                        "title": "Ingeniero de Infraestructura",
                        "url": "https://remotive.com/job/9999",
                        "company_name": None,
                        "salary": None,
                        "description": None,
                    }
                ]
            },
        ]

        for p in corrupted_payloads:
            parsed = remotive.parse_api_response(p)
            assert isinstance(parsed, list)

        # The last payload contains 1 valid job structure with fallback company
        valid_items = remotive.parse_api_response(corrupted_payloads[-1])
        assert len(valid_items) == 1
        assert valid_items[0].title == "Ingeniero de Infraestructura"
        assert valid_items[0].company == "Confidencial"


# =============================================================================
# 2. Normalizer Adversarial Deduplication & Boundary Testing
# =============================================================================

class TestNormalizerAdversarial:
    """Stress testing normalizer deduplication invariance and modality logic."""

    def test_adversarial_dedup_hash_invariance_under_noise(self):
        # 3 representations of the exact same job posting across different portals/states
        t1 = "[Remoto] Ingeniera Civil Especialista en Vías (Oferta destacada)"
        c1 = "4,8 Constructora Vías Andinas S.A.S."
        u1 = "https://co.computrabajo.com/ofertas/vias-123?utm_source=linkedin&utm_medium=cpc&position=1&pageNum=0#apply"

        t2 = "   ingeniera   civil especialista en vías  (Postulado) "
        c2 = "Constructora Vías Andinas S.A.S."
        u2 = "https://CO.COMPUTRABAJO.COM/ofertas/vias-123?trackingId=999&trk=feed#details"

        t3 = "Ingeniera Civil Especialista en Vías"
        c3 = "3.9 Constructora Vías Andinas S.A.S."
        u3 = "https://co.computrabajo.com/ofertas/vias-123"

        h1 = compute_dedup_id(t1, c1, u1)
        h2 = compute_dedup_id(t2, c2, u2)
        h3 = compute_dedup_id(t3, c3, u3)

        assert h1 == h2 == h3
        assert len(h1) == 16
        assert re.match(r"^[0-9a-f]{16}$", h1)

        # Different job yields different hash
        h_diff = compute_dedup_id("Ingeniero Geotécnico", c1, u1)
        assert h1 != h_diff

    def test_adversarial_tracking_parameter_comprehensive_stripping(self):
        raw_url = (
            "https://test.com/job/42?"
            "utm_source=google&UTM_MEDIUM=cpc&utm_campaign=brand&utm_term=job&utm_content=v1&"
            "position=3&pageNum=2&refId=x1&trackingId=y2&fbclid=z3&gclid=w4&trk=feed&ref=home&"
            "origin=search&f_WT=2&f_TPR=r86400&geoId=100876405&currentJobId=42&"
            "keep_param=important_value#target_fragment"
        )
        cleaned = clean_url(raw_url)
        assert cleaned == "https://test.com/job/42?keep_param=important_value"
        assert "utm_" not in cleaned.lower()
        assert "position" not in cleaned.lower()
        assert "#target_fragment" not in cleaned

    @pytest.mark.parametrize(
        "text,declared,expected",
        [
            ("Trabajo remoto para coordinación pero se requiere presencia en campamento y frente de obra", None, "presencial"),
            ("100% virtual pero abstenerse personas interesadas en trabajo remoto", None, "presencial"),
            ("Ingeniero de diseño vial, residencia en campamento minero", None, "presencial"),
            ("Turnos rotativos en sitio en planta industrial", "remoto", "presencial"),
            ("Esquema de alternancia 3 días en oficina y 2 días remotos", None, "hibrido"),
            ("Esquema mixto semipresencial", None, "hibrido"),
            ("100% teletrabajo nacional para diseño geométrico", None, "remoto"),
            ("Home office completo para consultoría", None, "remoto"),
            ("Completamente remoto desde cualquier lugar de Colombia", None, "remoto"),
            ("Especialista en pavimentos asfálticos con 15 años de experiencia", None, "desconocido"),
            ("", None, "desconocido"),
            (None, None, "desconocido"),
        ],
    )
    def test_adversarial_modality_safety_precedence(self, text, declared, expected):
        assert classify_modality(text, declared) == expected

    def test_adversarial_description_preserves_structure_strips_xss(self):
        dirty_desc = """
        <h1>Título Vacante</h1>
        <script>alert(document.cookie);</script>
        <p>Buscamos <b>Ingeniero Civil</b>.</p>
        <style>body { display: none; }</style>
        <ul>
            <li>Requisito 1: Tarjeta COPNIA</li>
            <li>Requisito 2: Especialización en Vías</li>
        </ul>
        <br><br><br><br>
        <p>Contacto: rrhh@empresa.com</p>
        """
        clean = clean_description(dirty_desc)
        assert "alert(" not in clean
        assert "<script>" not in clean
        assert "display: none" not in clean
        assert "Buscamos Ingeniero Civil" in clean
        assert "• Requisito 1: Tarjeta COPNIA" in clean
        assert "• Requisito 2: Especialización en Vías" in clean
        assert "Contacto: rrhh@empresa.com" in clean
        # Excessive newlines collapsed
        assert "\n\n\n" not in clean


# =============================================================================
# 3. Scrapers Partial DOM Extraction Challenges
# =============================================================================

class TestScrapersPartialDOMAdversarial:
    """Stress testing scraper parsing on minimalist or partially missing elements."""

    def test_adversarial_computrabajo_minimalist_card(self):
        mini_card = """
        <article class="box_offer">
            <h2><a class="js-o-link" href="/oferta/999">Ingeniero SST Remoto</a></h2>
        </article>
        """
        scraper = ComputrabajoScraper()
        vacs = scraper.parse_listings_html(mini_card)
        assert len(vacs) == 1
        assert vacs[0].title == "Ingeniero SST Remoto"
        assert vacs[0].company == "Confidencial"
        assert vacs[0].location == "Colombia"
        assert vacs[0].salary_range is None

    def test_adversarial_linkedin_minimalist_card(self):
        mini_card = """
        <ul><li>
            <div class="base-search-card">
                <h3 class="base-search-card__title">Director de Proyectos Viales</h3>
                <a class="base-card__full-link" href="https://linkedin.com/jobs/view/999">Ver</a>
            </div>
        </li></ul>
        """
        scraper = LinkedInScraper()
        vacs = scraper.parse_listings_html(mini_card)
        assert len(vacs) == 1
        assert vacs[0].title == "Director de Proyectos Viales"
        assert vacs[0].company == "Confidencial"
        assert vacs[0].location == "Colombia"


# =============================================================================
# 4. JobAggregationEngine Cascading Failure & Dedup Challenges
# =============================================================================

class TestJobAggregationEngineAdversarial:
    """Stress testing JobAggregationEngine under cascading scraper crashes."""

    def test_adversarial_cascading_portal_crashes_with_survivor(self):
        class CrashingScraper(BaseScraper):
            def __init__(self, exc):
                super().__init__()
                self.exc = exc

            def search(self, query, max_pages=1):
                raise self.exc

        class SurvivorScraper(BaseScraper):
            def search(self, query, max_pages=1):
                return [
                    normalize_vacancy("Surviving 1", "Co 1", "https://ok.com/1", "Desc", "survivor"),
                    normalize_vacancy("Surviving 2", "Co 2", "https://ok.com/2", "Desc", "survivor"),
                ]

        engine = JobAggregationEngine(
            custom_scrapers={
                "crash_net": CrashingScraper(HttpRequestError("429 Too Many Requests")),
                "crash_timeout": CrashingScraper(TimeoutError("Read timeout")),
                "crash_val": CrashingScraper(ValueError("Malformed payload")),
                "crash_runtime": CrashingScraper(RuntimeError("Catastrophic error")),
                "survivor": SurvivorScraper(),
            }
        )

        results = engine.run(
            queries=["civil"],
            portals=["crash_net", "crash_timeout", "crash_val", "crash_runtime", "survivor"]
        )

        assert len(results) == 2
        assert len(engine.last_run_stats["failures"]) == 4
        assert "crash_net" in engine.last_run_stats["failures"]
        assert "crash_timeout" in engine.last_run_stats["failures"]
        assert "crash_val" in engine.last_run_stats["failures"]
        assert "crash_runtime" in engine.last_run_stats["failures"]
        assert engine.last_run_stats["portal_counts"]["survivor"] == 2

    def test_adversarial_total_system_outage_graceful_degradation(self):
        class OutageScraper(BaseScraper):
            def search(self, query, max_pages=1):
                raise HttpRequestError("Global Portal Outage")

        engine = JobAggregationEngine(
            custom_scrapers={
                "outage1": OutageScraper(),
                "outage2": OutageScraper(),
            }
        )

        res = engine.run(queries=["vias"], portals=["outage1", "outage2"])
        assert res == []
        assert len(engine.last_run_stats["failures"]) == 2
        assert engine.last_run_stats["total_scraped"] == 0
        assert engine.last_run_stats["deduplicated_count"] == 0

    def test_adversarial_multi_query_cross_portal_global_dedup(self):
        class MultiDupScraper(BaseScraper):
            def search(self, query, max_pages=1):
                return [
                    normalize_vacancy(
                        "[Remoto] Ingeniero de Vías",
                        "Consorcio Vial 2026",
                        "https://portal.com/job/50?utm_source=feed",
                        "Desc A",
                        "dup_portal",
                    ),
                    normalize_vacancy(
                        "ingeniero de vías",
                        "4,9 Consorcio Vial 2026",
                        "https://portal.com/job/50#apply",
                        "Desc B",
                        "dup_portal",
                    ),
                    normalize_vacancy(
                        "Otro Puesto Distinto",
                        "Consorcio Vial 2026",
                        "https://portal.com/job/51",
                        "Desc C",
                        "dup_portal",
                    ),
                ]

        engine = JobAggregationEngine(custom_scrapers={"dup": MultiDupScraper()})
        res = engine.run(queries=["q1", "q2"], portals=["dup"])

        # 3 items per query * 2 queries = 6 total scraped, but only 2 unique IDs
        assert engine.last_run_stats["total_scraped"] == 6
        assert engine.last_run_stats["deduplicated_count"] == 2
        assert len(res) == 2

    def test_adversarial_empty_queries_and_invalid_portal_names(self):
        engine = JobAggregationEngine()
        # Empty queries defaults safely
        res_empty = engine.run(queries=[], offline=True)
        assert len(res_empty) > 0

        # Invalid portal names ignored gracefully
        res_invalid = engine.run(queries=["vias"], portals=["non_existent_portal_123"])
        assert res_invalid == []
