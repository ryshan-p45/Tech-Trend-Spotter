import asyncio
import logging

import httpx
import pytest
from pydantic import ValidationError

from functionality.data_collection.collectors.advisory.github_advisories import GitHubAdvisoriesCollector
from functionality.data_collection.http_client import SourceHttpClient
from interfaces.source_config_interfaces import GitHubAdvisoriesConfig

"""Tests for the GitHub Security Advisories collector using fixed, recorded-style API responses."""


API_URL = "https://api.github.test/advisories"
CONFIG = GitHubAdvisoriesConfig(api_url=API_URL, lookback_days=7, max_pages=3)


def advisory(**overrides):
    """One advisory in the real GitHub API shape (trimmed to the fields we use)."""
    record = {
        "ghsa_id": "GHSA-j44m-77cc-p3cc",
        "cve_id": "CVE-2026-63492",
        "html_url": "https://github.com/advisories/GHSA-j44m-77cc-p3cc",
        "summary": "AVideo API vulnerable to OS command injection",
        "description": "An unescaped FFmpeg keyword allows command injection.",
        "type": "reviewed",
        "severity": "high",
        "published_at": "2026-11-23T22:06:28Z",
        "withdrawn_at": None,
        "vulnerabilities": [
            {"package": {"ecosystem": "composer", "name": "wwbn/avideo"},
             "vulnerable_version_range": "< 29.1.0", "first_patched_version": "29.1.0"},
        ],
        "cwes": [{"cwe_id": "CWE-78", "name": "OS Command Injection"}],
        "credits": [{"user": {"login": "someone"}, "type": "reporter"}],
    }
    return {**record, **overrides}


def make_http(handler):
    return SourceHttpClient(httpx.AsyncClient(transport=httpx.MockTransport(handler)),
                            max_attempts=1, backoff_base_seconds=0)


def run_collector(body, status=200, config=CONFIG, api_token=None):
    """Runs the collector against a mocked API returning a single page with `body`."""
    http = make_http(lambda request: httpx.Response(status, json=body))
    return asyncio.run(GitHubAdvisoriesCollector(config, api_token=api_token).collect(http, correlation_id="test"))


def paged_handler(pages, seen):
    """Serves `pages` in order, linking each to the next via a Link header. Records requests in `seen`."""
    def handler(request):
        index = int(request.url.params.get("page_index", "0"))
        seen.append(request)
        headers = {}
        if index + 1 < len(pages):
            headers["Link"] = f'<{API_URL}?page_index={index + 1}>; rel="next"'
        return httpx.Response(200, json=pages[index], headers=headers)
    return handler


def test_parses_advisory():
    result = run_collector([advisory()])

    assert result.status == "success"
    assert result.source_type == "advisory"
    item = result.items[0]
    assert item.external_id == "GHSA-j44m-77cc-p3cc"
    assert item.cve_id == "CVE-2026-63492"
    assert item.title == "AVideo API vulnerable to OS command injection"
    assert str(item.url) == "https://github.com/advisories/GHSA-j44m-77cc-p3cc"
    assert item.severity == "high"
    assert item.tags == ["CWE-78"]
    assert item.known_exploited is False
    assert item.published_at.tzinfo is not None
    assert [(a.vendor, a.product, a.ecosystem) for a in item.affected] == [(None, "wwbn/avideo", "composer")]


def test_multiple_packages_stay_one_item():
    record = advisory(vulnerabilities=[
        {"package": {"ecosystem": "npm", "name": "pkg-a"}},
        {"package": {"ecosystem": "pip", "name": "pkg-b"}},
        {"package": {"ecosystem": "npm", "name": None}},  # nameless packages are left out
    ])
    result = run_collector([record])

    assert len(result.items) == 1
    assert [a.product for a in result.items[0].affected] == ["pkg-a", "pkg-b"]


def test_package_listed_once_per_version_range_is_not_duplicated():
    record = advisory(vulnerabilities=[
        {"package": {"ecosystem": "maven", "name": "org.jline:jline-builtins"}, "vulnerable_version_range": "< 3.0"},
        {"package": {"ecosystem": "maven", "name": "org.jline:jline-builtins"}, "vulnerable_version_range": ">= 4.0, < 4.1"},
    ])
    affected = run_collector([record]).items[0].affected
    assert [a.product for a in affected] == ["org.jline:jline-builtins"]


def test_reporter_usernames_are_not_kept():
    item = run_collector([advisory()]).items[0]
    assert "credits" not in item.raw_payload


@pytest.mark.parametrize("value, expected", [("critical", "critical"), ("low", "low"), ("unknown", None), (None, None)])
def test_maps_severity(value, expected):
    assert run_collector([advisory(severity=value)]).items[0].severity == expected


def test_advisory_without_cve_is_kept():
    assert run_collector([advisory(cve_id=None)]).items[0].cve_id is None


def test_long_summary_is_truncated_not_rejected():
    item = run_collector([advisory(summary="x" * 600)]).items[0]
    assert len(item.title) == 500


def test_withdrawn_advisories_are_dropped():
    result = run_collector([advisory(), advisory(ghsa_id="GHSA-xxxx-xxxx-xxxx", withdrawn_at="2026-11-23T00:00:00Z")])
    assert [item.external_id for item in result.items] == ["GHSA-j44m-77cc-p3cc"]
    assert result.skipped_count == 0


def test_invalid_records_are_skipped_not_fatal():
    missing_summary = {k: v for k, v in advisory(ghsa_id="GHSA-aaaa").items() if k != "summary"}
    bad_cve = advisory(ghsa_id="GHSA-bbbb", cve_id="not-a-cve")
    result = run_collector([advisory(), missing_summary, bad_cve, "not a dict"])

    assert result.status == "success"
    assert len(result.items) == 1
    assert result.skipped_count == 3


def test_first_request_filters_reviewed_recent_newest_first():
    seen = []
    http = make_http(paged_handler([[]], seen))
    asyncio.run(GitHubAdvisoriesCollector(CONFIG).collect(http, correlation_id="test"))

    params = seen[0].url.params
    assert seen[0].url.host == "api.github.test"
    assert params["type"] == "reviewed"
    assert params["published"].startswith(">=")
    assert params["sort"] == "published"
    assert params["per_page"] == "100"


def test_follows_next_links_across_pages():
    seen = []
    pages = [[advisory(ghsa_id="GHSA-1")], [advisory(ghsa_id="GHSA-2")]]
    http = make_http(paged_handler(pages, seen))
    result = asyncio.run(GitHubAdvisoriesCollector(CONFIG).collect(http, correlation_id="test"))

    assert [item.external_id for item in result.items] == ["GHSA-1", "GHSA-2"]
    assert len(seen) == 2


def test_stops_at_max_pages_and_logs_warning(caplog):
    seen = []
    pages = [[advisory(ghsa_id=f"GHSA-{i}")] for i in range(5)]
    http = make_http(paged_handler(pages, seen))
    with caplog.at_level(logging.WARNING):
        result = asyncio.run(GitHubAdvisoriesCollector(CONFIG).collect(http, correlation_id="test"))

    assert len(seen) == 3  # CONFIG.max_pages
    assert len(result.items) == 3
    assert "Page limit reached" in caplog.text


def test_refuses_next_link_to_another_host():
    def handler(request):
        return httpx.Response(200, json=[advisory()], headers={"Link": '<https://evil.test/steal>; rel="next"'})

    result = asyncio.run(GitHubAdvisoriesCollector(CONFIG, api_token="secret").collect(make_http(handler), correlation_id="test"))
    assert result.status == "failed"
    assert result.error.category == "non_retryable"


def test_sends_token_only_when_configured():
    seen = []

    def handler(request):
        seen.append(request.headers)
        return httpx.Response(200, json=[])

    asyncio.run(GitHubAdvisoriesCollector(CONFIG).collect(make_http(handler), correlation_id="test"))
    asyncio.run(GitHubAdvisoriesCollector(CONFIG, api_token="secret").collect(make_http(handler), correlation_id="test"))

    assert "Authorization" not in seen[0]
    assert seen[1]["Authorization"] == "Bearer secret"
    assert seen[1]["Accept"] == "application/vnd.github+json"


def test_token_is_never_logged(caplog):
    with caplog.at_level(logging.DEBUG):
        run_collector([advisory()], api_token="super-secret-token")
        run_collector({}, status=403, api_token="super-secret-token")
    assert "super-secret-token" not in caplog.text


def test_unexpected_response_shape_fails_as_non_retryable():
    result = run_collector({"message": "not a list"})
    assert result.status == "failed"
    assert result.error.category == "non_retryable"


def test_server_error_fails_as_retryable():
    result = run_collector({}, status=503)
    assert result.status == "failed"
    assert result.error.category == "retryable"


@pytest.mark.parametrize("override", [
    {"lookback_days": 0},
    {"lookback_days": 366},
    {"max_pages": 0},
    {"max_pages": 31},
    {"api_url": "http://api.github.test/advisories"},
    {"unknown_key": True},
])
def test_rejects_invalid_config(override):
    with pytest.raises(ValidationError):
        GitHubAdvisoriesConfig(**{**CONFIG.model_dump(mode="json"), **override})
