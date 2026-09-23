"""Resilient HTTP client for job board scraping with rate limiting, retries, and circuit breaker.

Features:
- Rotating realistic desktop browser User-Agents
- Jittered rate limiting per domain/host (1.0s - 2.5s)
- Exponential backoff retries on HTTP 429, 500, 502, 503, 504 and network errors
- Retry-After header parsing for HTTP 429
- Per-domain circuit breaker pattern isolating portal failures
- Windows encoding safe logging
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

import requests

logger = logging.getLogger(__name__)

USER_AGENT_POOL: List[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 Edg/128.0.0.0",
]

DEFAULT_HEADERS: Dict[str, str] = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "es-CO,es;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate",
    "Sec-Ch-Ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class HttpClientError(Exception):
    """Base exception for HttpClient errors."""
    pass


class CircuitBreakerOpenError(HttpClientError):
    """Raised when request is prevented because circuit breaker for host is open."""
    pass


class HttpRequestError(HttpClientError):
    """Raised when an HTTP request fails after exhausting retry budget."""
    pass


class CircuitBreaker:
    """Manages failure counts and temporary cool-down blocks per domain."""

    def __init__(self, failure_threshold: int = 4, cooldown_seconds: float = 60.0):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self._failures: Dict[str, int] = {}
        self._tripped_until: Dict[str, float] = {}

    def is_open(self, host: str) -> bool:
        """Check if circuit breaker for host is active/tripped."""
        until = self._tripped_until.get(host, 0.0)
        if until > time.time():
            return True
        if until > 0.0:
            # Cool-down expired; half-open reset
            self._tripped_until.pop(host, None)
            self._failures[host] = 0
        return False

    def record_success(self, host: str) -> None:
        """Reset failure counter on successful response."""
        self._failures[host] = 0
        self._tripped_until.pop(host, None)

    def record_failure(self, host: str) -> None:
        """Increment failure counter and trip breaker if threshold exceeded."""
        current = self._failures.get(host, 0) + 1
        self._failures[host] = current
        if current >= self.failure_threshold:
            self._tripped_until[host] = time.time() + self.cooldown_seconds
            logger.warning(
                f"Circuit breaker TRIPPED for host '{host}' after {current} consecutive failures. "
                f"Cooling down for {self.cooldown_seconds}s."
            )

    def reset(self, host: Optional[str] = None) -> None:
        """Reset circuit breaker for specific host or all hosts."""
        if host:
            self._failures.pop(host, None)
            self._tripped_until.pop(host, None)
        else:
            self._failures.clear()
            self._tripped_until.clear()


class HttpClient:
    """Resilient HTTP client with User-Agent rotation, rate limiting, and retries."""

    def __init__(
        self,
        rate_limit_delay: float = 1.0,
        jitter_min: float = 0.5,
        jitter_max: float = 1.5,
        max_retries: int = 3,
        timeout: float = 15.0,
        circuit_threshold: int = 4,
        circuit_cooldown: float = 60.0,
        session: Optional[requests.Session] = None,
    ):
        self.rate_limit_delay = rate_limit_delay
        self.jitter_min = jitter_min
        self.jitter_max = jitter_max
        self.max_retries = max_retries
        self.timeout = timeout
        self.session = session or requests.Session()
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=circuit_threshold,
            cooldown_seconds=circuit_cooldown,
        )
        self._last_request_time: Dict[str, float] = {}

    def _extract_host(self, url: str) -> str:
        """Extract netloc host from URL."""
        return urlsplit(url).netloc.lower() or "default"

    def _build_headers(self, custom_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """Construct headers with randomized User-Agent and defaults."""
        headers = dict(DEFAULT_HEADERS)
        headers["User-Agent"] = random.choice(USER_AGENT_POOL)
        if custom_headers:
            headers.update(custom_headers)
        return headers

    def _throttle(self, host: str) -> None:
        """Enforce rate limit delay with random jitter per host."""
        if self.rate_limit_delay <= 0.0:
            return

        last_time = self._last_request_time.get(host, 0.0)
        elapsed = time.time() - last_time
        jitter = random.uniform(self.jitter_min, self.jitter_max)
        target_delay = self.rate_limit_delay + jitter

        if elapsed < target_delay:
            wait_time = target_delay - elapsed
            time.sleep(wait_time)

        self._last_request_time[host] = time.time()

    def get(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
        allow_redirects: bool = True,
    ) -> requests.Response:
        """Send GET request with retries, exponential backoff, rate limiting, and circuit breaker."""
        host = self._extract_host(url)

        if self.circuit_breaker.is_open(host):
            raise CircuitBreakerOpenError(
                f"Circuit breaker is open for host '{host}'. Requests to this portal are temporarily halted."
            )

        req_timeout = timeout if timeout is not None else self.timeout
        last_exception: Optional[Exception] = None
        last_response: Optional[requests.Response] = None

        for attempt in range(self.max_retries + 1):
            self._throttle(host)
            req_headers = self._build_headers(headers)

            try:
                response = self.session.get(
                    url,
                    params=params,
                    headers=req_headers,
                    timeout=req_timeout,
                    allow_redirects=allow_redirects,
                )

                if response.status_code in RETRYABLE_STATUS_CODES:
                    last_response = response
                    if attempt < self.max_retries:
                        backoff = self._calculate_backoff(attempt, response)
                        logger.warning(
                            f"HTTP {response.status_code} on {url} (attempt {attempt + 1}/{self.max_retries + 1}). "
                            f"Backing off {backoff:.2f}s."
                        )
                        time.sleep(backoff)
                        continue
                    else:
                        # Exceeded retries on retryable HTTP status
                        self.circuit_breaker.record_failure(host)
                        raise HttpRequestError(
                            f"HTTP {response.status_code} received from {url} after {self.max_retries + 1} attempts."
                        )

                # Successful or non-retryable response (e.g. 200, 404)
                self.circuit_breaker.record_success(host)
                return response

            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                last_exception = e
                if attempt < self.max_retries:
                    backoff = min(30.0, (2 ** attempt) + random.uniform(0.2, 1.0))
                    logger.warning(
                        f"Network error on {url} ({e.__class__.__name__}). Attempt {attempt + 1}. Retrying in {backoff:.2f}s."
                    )
                    time.sleep(backoff)
                else:
                    self.circuit_breaker.record_failure(host)
                    raise HttpRequestError(f"Network error on {url} after {self.max_retries + 1} attempts: {e}") from e

            except requests.exceptions.RequestException as e:
                self.circuit_breaker.record_failure(host)
                raise HttpRequestError(f"Fatal request exception on {url}: {e}") from e

        # Fallback if somehow loop exited
        self.circuit_breaker.record_failure(host)
        if last_response is not None:
            raise HttpRequestError(f"Request failed with status {last_response.status_code} on {url}")
        raise HttpRequestError(f"Request failed on {url}: {last_exception}")

    def _calculate_backoff(self, attempt: int, response: requests.Response) -> float:
        """Calculate backoff duration, respecting Retry-After header if present."""
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    val = float(retry_after)
                    return min(30.0, max(1.0, val))
                except ValueError:
                    pass
        # Exponential backoff: 2s, 4s, 8s with jitter
        return min(30.0, (2 ** (attempt + 1)) + random.uniform(0.2, 1.0))

    def get_html(self, url: str, params: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Convenience method returning decoded HTML string or None on failure."""
        try:
            resp = self.get(url, params=params)
            if resp.status_code == 200:
                return resp.text
            return None
        except HttpClientError as e:
            logger.error(f"Failed to fetch HTML from {url}: {e}")
            return None

    def get_json(self, url: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Convenience method returning parsed JSON dict or None on failure."""
        try:
            resp = self.get(url, params=params)
            if resp.status_code == 200:
                return resp.json()
            return None
        except (HttpClientError, ValueError) as e:
            logger.error(f"Failed to fetch JSON from {url}: {e}")
            return None
