import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from pydantic import ValidationError

from functionality.data_collection.collectors.advisory.cisa_kev import CisaKevCollector
from functionality.data_collection.http_client import SourceHttpClient
from interfaces.collection_interfaces import Advisory
from interfaces.source_config_interfaces import CisaKevConfig

"""Tests for the CISA KEV collector using a fixed, recorded-style catalog response."""


CONFIG = CisaKevConfig(feed_url="https://kev.test/known_exploited_vulnerabilities.json", lookback_days=30)

TODAY = datetime.now(timezone.utc).date()


def kev_entry(**overrides):
    """One catalog entry in the real KEV shape, added today unless overridden."""
    entry = {
        "cveID": "CVE-2026-133968",
        "vendorProject": "Project MONAI",
        "product": "MONAI Label",
        "vulnerabilityName": "Project MONAI MONAI Label Path Traversal Vulnerability",
        "dateAdded": TODAY.isoformat(),
        "shortDescription": "Path traversal allowing an unauthenticated attacker to write arbitrary files.",
        "requiredAction": "Apply mitigations per vendor instructions.",
        "dueDate": (TODAY + timedelta(days=3)).isoformat(),
        "knownRansomwareCampaignUse": "Unknown",
        "notes": "https://nvd.nist.gov/vuln/detail/CVE-2026-133968",
        "cwes": ["CWE-24"],
    }
    return {**entry, **overrides}


def catalog(*entries):
    return {"title": "CISA Catalog of Known Exploited Vulnerabilities", "count": len(entries),
            "vulnerabilities": list(entries)}


def run_collector(body, status=200, config=CONFIG):
    """Runs the collector against a mocked KEV feed that returns `body`."""
    transport = httpx.MockTransport(lambda request: httpx.Response(status, json=body))
    http = SourceHttpClient(httpx.AsyncClient(transport=transport), max_attempts=1, backoff_base_seconds=0)
    return asyncio.run(CisaKevCollector(config).collect(http, correlation_id="test"))


def test_parses_entry_into_advisory():
    result = run_collector(catalog(kev_entry()))

    assert result.status == "success"
    assert result.source_type == "advisory"
    advisory = result.items[0]
    assert advisory.cve_id == "CVE-2026-133968"
    assert advisory.external_id == "CVE-2026-133968"
    assert len(advisory.affected) == 1
    assert advisory.affected[0].vendor == "Project MONAI"
    assert advisory.affected[0].product == "MONAI Label"
    assert advisory.affected[0].ecosystem is None
    assert advisory.title == "Project MONAI MONAI Label Path Traversal Vulnerability"
    assert str(advisory.url) == "https://nvd.nist.gov/vuln/detail/CVE-2026-133968"
    assert advisory.tags == ["CWE-24"]
    assert advisory.known_exploited is True
    assert advisory.known_ransomware_use is False
    assert advisory.severity is None
    assert advisory.remediation_due_date == TODAY + timedelta(days=3)
    assert advisory.published_at == datetime.combine(TODAY, datetime.min.time(), tzinfo=timezone.utc)


def test_same_cve_gets_same_item_id_across_runs():
    first = run_collector(catalog(kev_entry())).items[0]
    second = run_collector(catalog(kev_entry())).items[0]
    assert first.item_id == second.item_id


@pytest.mark.parametrize("value, expected", [("Known", True), ("Unknown", False), ("Something new", None)])
def test_maps_ransomware_use(value, expected):
    advisory = run_collector(catalog(kev_entry(knownRansomwareCampaignUse=value))).items[0]
    assert advisory.known_ransomware_use is expected


def test_entries_older_than_lookback_are_dropped():
    old = kev_entry(cveID="CVE-2020-0001", dateAdded=(TODAY - timedelta(days=31)).isoformat())
    edge = kev_entry(cveID="CVE-2026-0002", dateAdded=(TODAY - timedelta(days=30)).isoformat())
    result = run_collector(catalog(kev_entry(), old, edge))

    assert [item.cve_id for item in result.items] == ["CVE-2026-133968", "CVE-2026-0002"]
    assert result.skipped_count == 0  # out-of-window entries are filtered, not "skipped"


def test_invalid_entries_are_skipped_not_fatal():
    bad_cve = kev_entry(cveID="not-a-cve")
    bad_date = kev_entry(cveID="CVE-2026-0003", dateAdded="23/11/2026")
    missing_name = {k: v for k, v in kev_entry(cveID="CVE-2026-0004").items() if k != "vulnerabilityName"}
    result = run_collector(catalog(kev_entry(), bad_cve, bad_date, missing_name, "not a dict"))

    assert result.status == "success"
    assert len(result.items) == 1
    assert result.skipped_count == 4


def test_entry_without_product_has_no_affected_products():
    advisory = run_collector(catalog(kev_entry(product=""))).items[0]
    assert advisory.affected == []


def test_missing_optional_fields_become_null():
    entry = kev_entry(vendorProject="", dueDate=None, cwes=[])
    del entry["shortDescription"]
    advisory = run_collector(catalog(entry)).items[0]

    assert advisory.affected[0].vendor is None
    assert advisory.content is None
    assert advisory.remediation_due_date is None
    assert advisory.tags == []


def test_unexpected_response_shape_fails_as_non_retryable():
    result = run_collector({"unexpected": True})
    assert result.status == "failed"
    assert result.items == []
    assert result.error.category == "non_retryable"


def test_server_error_fails_as_retryable():
    result = run_collector({}, status=503)
    assert result.status == "failed"
    assert result.error.category == "retryable"


def test_uses_configured_feed_url():
    seen = []

    def handler(request):
        seen.append(request.url)
        return httpx.Response(200, json=catalog())

    http = SourceHttpClient(httpx.AsyncClient(transport=httpx.MockTransport(handler)), max_attempts=1)
    asyncio.run(CisaKevCollector(CONFIG).collect(http, correlation_id="test"))

    assert str(seen[0]) == "https://kev.test/known_exploited_vulnerabilities.json"


@pytest.mark.parametrize("override", [
    {"lookback_days": 0},
    {"lookback_days": 3651},
    {"feed_url": "http://kev.test/feed.json"},
    {"unknown_key": True},
])
def test_rejects_invalid_config(override):
    with pytest.raises(ValidationError):
        CisaKevConfig(**{**CONFIG.model_dump(mode="json"), **override})


def test_advisory_model_validates_cve_id_format():
    valid = run_collector(catalog(kev_entry())).items[0].model_dump()
    with pytest.raises(ValidationError):
        Advisory(**{**valid, "cve_id": "CVE-26-1"})
    assert Advisory(**{**valid, "cve_id": None}).cve_id is None  # advisories without a CVE are allowed
