import asyncio

import httpx
import pytest

from functionality.data_collection.http_client import CircuitBreaker, FetchError, SourceHttpClient

"""
Tests for the shared HTTP client: retry rules, circuit breaker and robots.txt.
All network traffic goes through httpx.MockTransport - no real requests are made.
"""


def make_client(handler) -> SourceHttpClient:
    """SourceHttpClient over a mocked transport, with zero backoff so tests run instantly."""
    return SourceHttpClient(httpx.AsyncClient(transport=httpx.MockTransport(handler)),
                            max_attempts=3, backoff_base_seconds=0, backoff_max_seconds=0)


def test_retries_retryable_status_then_succeeds():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503) if len(calls) < 3 else httpx.Response(200, json={"ok": True})

    body = asyncio.run(make_client(handler).get_json("https://api.test/x", check_robots=False, correlation_id="t"))
    assert body == {"ok": True}
    assert len(calls) == 3


def test_does_not_retry_client_errors():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(404)

    with pytest.raises(FetchError) as error:
        asyncio.run(make_client(handler).get_json("https://api.test/x", check_robots=False, correlation_id="t"))
    assert error.value.retryable is False
    assert len(calls) == 1


def test_timeout_is_retryable_and_stops_after_max_attempts():
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(FetchError) as error:
        asyncio.run(make_client(handler).get_json("https://api.test/x", check_robots=False, correlation_id="t"))
    assert error.value.retryable is True
    assert len(calls) == 3


def test_invalid_json_is_non_retryable():
    client = make_client(lambda request: httpx.Response(200, text="<html>not json</html>"))
    with pytest.raises(FetchError) as error:
        asyncio.run(client.get_json("https://api.test/x", check_robots=False, correlation_id="t"))
    assert error.value.retryable is False


def test_robots_disallow_blocks_request():
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private/")
        return httpx.Response(200, content=b"data")

    client = make_client(handler)
    assert asyncio.run(client.get_bytes("https://site.test/public/feed", check_robots=True, correlation_id="t")) == b"data"
    with pytest.raises(FetchError) as error:
        asyncio.run(client.get_bytes("https://site.test/private/feed", check_robots=True, correlation_id="t"))
    assert error.value.retryable is False


def test_missing_robots_allows_everything():
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, content=b"data")

    result = asyncio.run(make_client(handler).get_bytes("https://site.test/feed", check_robots=True, correlation_id="t"))
    assert result == b"data"


def test_circuit_breaker_opens_after_threshold_and_resets_after_cooldown():
    now = [0.0]
    breaker = CircuitBreaker(failure_threshold=2, reset_after_seconds=60, clock=lambda: now[0])

    breaker.record_failure()
    assert breaker.allows_request()
    breaker.record_failure()
    assert not breaker.allows_request()

    now[0] = 61.0
    assert breaker.allows_request()
    breaker.record_success()
    assert breaker.allows_request()
