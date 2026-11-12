import time
from typing import Any, Callable
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential

from app_logging import get_logger
from config import COLLECTOR_USER_AGENT

"""
Shared, polite HTTP client used by every collector.

Collectors never call httpx directly - they go through SourceHttpClient so
every external call gets the same reliability and safety rules:
    - Timeout on every request (configured on the httpx client)
    - Retries with exponential backoff, ONLY for retryable errors
      (timeouts, connection errors, 429, 5xx). 4xx errors fail immediately.
    - A circuit breaker per host: after repeated failures we stop calling
      that host for a cool-down period instead of hammering it.
    - Optional robots.txt check for websites (APIs are exempt - they are
      designed for programmatic access).
    - A maximum response size so a misbehaving source can't exhaust memory.
    - One structured log line per call: service, action, status, duration.

Note: circuit breaker and robots.txt state is held in memory per client
instance (i.e. per collection run). That is acceptable for now because it
only affects politeness, not data. Move it to the database if collection
is ever split across multiple workers.
"""


logger = get_logger("data_collection.http")

# Hard limit on how much data we accept from any single response (5 MB)
MAX_RESPONSE_BYTES = 5 * 1024 * 1024

# HTTP statuses that mean "try again later" rather than "your request is wrong"
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class FetchError(Exception):
    """Raised when a request ultimately fails. `retryable` tells the caller whether a later run might succeed."""

    def __init__(self, message: str, retryable: bool):
        super().__init__(message)
        self.retryable = retryable


class CircuitBreaker:
    """
    Tracks consecutive failures for one host.

    CLOSED (normal)  -> requests allowed
    OPEN             -> after `failure_threshold` consecutive failures; requests
                        blocked until `reset_after_seconds` have passed
    After the cool-down one trial request is allowed; success closes the
    circuit again, failure re-opens it.
    """

    def __init__(self, failure_threshold: int = 5, reset_after_seconds: float = 300.0,
                 clock: Callable[[], float] = time.monotonic):
        self.failure_threshold = failure_threshold
        self.reset_after_seconds = reset_after_seconds
        self._clock = clock
        self._consecutive_failures = 0
        self._opened_at: float | None = None

    def allows_request(self) -> bool:
        """True if the circuit is closed, or open long enough to allow a trial request."""
        if self._opened_at is None:
            return True
        return self._clock() - self._opened_at >= self.reset_after_seconds

    def record_success(self) -> None:
        self._consecutive_failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.failure_threshold:
            self._opened_at = self._clock()


def _is_retryable(error: BaseException) -> bool:
    """Used by tenacity to decide whether to retry a failed attempt."""
    return isinstance(error, FetchError) and error.retryable


class SourceHttpClient:
    """Wraps an httpx.AsyncClient with retries, circuit breakers and robots.txt checks."""

    def __init__(self, client: httpx.AsyncClient, max_attempts: int = 3,
                 backoff_base_seconds: float = 1.0, backoff_max_seconds: float = 30.0):
        self._client = client
        self._max_attempts = max_attempts
        self._backoff_base_seconds = backoff_base_seconds
        self._backoff_max_seconds = backoff_max_seconds
        self._breakers: dict[str, CircuitBreaker] = {}
        self._robots_cache: dict[str, RobotFileParser] = {}

    # ---------- Public API used by collectors ----------

    async def get_json(self, url: str, *, params: dict[str, Any] | None = None,
                       check_robots: bool, correlation_id: str) -> Any:
        """GET a URL and return the parsed JSON body. Raises FetchError on failure."""
        response = await self._get(url, params=params, check_robots=check_robots, correlation_id=correlation_id)
        try:
            return response.json()
        except ValueError as error:
            # The source answered but not with JSON - retrying won't fix that
            raise FetchError(f"Response from {url} was not valid JSON: {error}", retryable=False) from error

    async def get_bytes(self, url: str, *, check_robots: bool, correlation_id: str) -> bytes:
        """GET a URL and return the raw body (e.g. an RSS/Atom feed). Raises FetchError on failure."""
        response = await self._get(url, params=None, check_robots=check_robots, correlation_id=correlation_id)
        return response.content

    # ---------- Internals ----------

    async def _get(self, url: str, *, params: dict[str, Any] | None,
                   check_robots: bool, correlation_id: str) -> httpx.Response:
        """Runs the guarded request: circuit breaker -> robots.txt -> request with retries."""
        host = urlsplit(url).netloc
        breaker = self._breakers.setdefault(host, CircuitBreaker())

        if not breaker.allows_request():
            raise FetchError(f"Circuit open for {host}; skipping request until cool-down ends", retryable=True)

        if check_robots and not await self._robots_allows(url, correlation_id):
            raise FetchError(f"robots.txt for {host} disallows fetching {url}", retryable=False)

        try:
            response = await self._send_with_retries(url, params, correlation_id)
        except FetchError as error:
            # Only count failures the source is responsible for (not e.g. 404s or size rejections)
            if error.retryable:
                breaker.record_failure()
            logger.error("External request failed", extra={
                "correlation_id": correlation_id,
                "context": {"url": url, "retryable": error.retryable, "error": str(error)},
            })
            raise

        breaker.record_success()
        return response

    async def _send_with_retries(self, url: str, params: dict[str, Any] | None,
                                 correlation_id: str) -> httpx.Response:
        """Calls _send_once, retrying retryable failures with exponential backoff up to max_attempts."""
        retrying = AsyncRetrying(
            stop=stop_after_attempt(self._max_attempts),
            wait=wait_exponential(multiplier=self._backoff_base_seconds, max=self._backoff_max_seconds),
            retry=retry_if_exception(_is_retryable),
            reraise=True,  # surface the original FetchError, not tenacity's RetryError
        )
        async for attempt in retrying:
            with attempt:
                if attempt.retry_state.attempt_number > 1:
                    logger.warning("Retrying external request", extra={
                        "correlation_id": correlation_id,
                        "context": {"url": url, "attempt": attempt.retry_state.attempt_number},
                    })
                return await self._send_once(url, params, correlation_id)
        raise FetchError(f"Retry loop for {url} ended without a result", retryable=False)  # unreachable safeguard

    async def _send_once(self, url: str, params: dict[str, Any] | None, correlation_id: str) -> httpx.Response:
        """One HTTP attempt. Converts every failure into a FetchError with the right retryable flag."""
        started = time.perf_counter()
        try:
            response = await self._client.get(url, params=params)
        except httpx.TimeoutException as error:
            raise FetchError(f"Timed out requesting {url}", retryable=True) from error
        except httpx.TransportError as error:
            raise FetchError(f"Connection error requesting {url}: {error}", retryable=True) from error

        duration_ms = round((time.perf_counter() - started) * 1000)
        logger.info("External request", extra={
            "correlation_id": correlation_id,
            "context": {"service": urlsplit(url).netloc, "action": "GET", "url": url,
                        "status": response.status_code, "duration_ms": duration_ms},
        })

        if response.status_code in RETRYABLE_STATUS_CODES:
            raise FetchError(f"{url} returned retryable status {response.status_code}", retryable=True)
        if response.status_code >= 400:
            raise FetchError(f"{url} returned status {response.status_code}", retryable=False)
        if len(response.content) > MAX_RESPONSE_BYTES:
            raise FetchError(f"{url} response exceeded {MAX_RESPONSE_BYTES} bytes", retryable=False)

        return response

    async def _robots_allows(self, url: str, correlation_id: str) -> bool:
        """
        Checks robots.txt for the URL's host (cached per host).
        Follows RFC 9309: a missing robots.txt (4xx) means everything is allowed;
        an unreachable one (5xx / network error) means assume nothing is allowed.
        """
        parts = urlsplit(url)
        host = parts.netloc

        if host not in self._robots_cache:
            parser = RobotFileParser()
            robots_url = f"{parts.scheme}://{host}/robots.txt"
            try:
                response = await self._client.get(robots_url)
                if response.status_code >= 500:
                    parser.disallow_all = True
                elif response.status_code >= 400:
                    parser.allow_all = True
                else:
                    parser.parse(response.text.splitlines())
            except httpx.HTTPError as error:
                logger.warning("Could not fetch robots.txt; treating host as disallowed", extra={
                    "correlation_id": correlation_id,
                    "context": {"robots_url": robots_url, "error": str(error)},
                })
                parser.disallow_all = True
            self._robots_cache[host] = parser

        return self._robots_cache[host].can_fetch(COLLECTOR_USER_AGENT, url)
