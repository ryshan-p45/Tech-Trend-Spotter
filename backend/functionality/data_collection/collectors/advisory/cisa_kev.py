from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from functionality.data_collection.collectors.base import (
    BaseCollector, SourceFormatError, to_json_safe, truncate_content,
)
from functionality.data_collection.http_client import SourceHttpClient
from interfaces.collection_interfaces import Advisory, build_item_id
from interfaces.source_config_interfaces import CisaKevConfig

"""
CISA Known Exploited Vulnerabilities (KEV) collector (advisory source).

The KEV catalog lists vulnerabilities that are confirmed to be exploited in
the wild, each naming the affected vendor and product. That makes it a
strong signal for finding potential clients. It is a free, key-less JSON feed:
    https://www.cisa.gov/known-exploited-vulnerabilities-catalog

The feed is the whole catalog (~1,800 entries, ~2 MB) in one file, so we
download it once per run and keep only entries added in the last
`lookback_days` (sources.yaml: advisory.cisa_kev).

Notes on mapping:
    - published_at is the date CISA ADDED the entry to KEV (not the CVE's
      original publication date). That is the date that matters for trends.
    - KEV does not rate severity, so severity is null. Severity can be
      enriched later from NVD.
"""


# Public NVD page for a CVE, used as the item link (KEV entries have no page of their own)
NVD_CVE_URL_TEMPLATE = "https://nvd.nist.gov/vuln/detail/{cve_id}"

# KEV's knownRansomwareCampaignUse values -> our boolean (anything else becomes null)
RANSOMWARE_USE_VALUES = {"Known": True, "Unknown": False}


class CisaKevCollector(BaseCollector):
    """Collects recently added entries from the CISA KEV catalog."""

    source_name = "cisa_kev"
    source_type = "advisory"

    def __init__(self, config: CisaKevConfig):
        # Config is validated by the pydantic model (https URL, lookback range)
        self.config = config

    async def fetch_records(self, http: SourceHttpClient, correlation_id: str) -> list[dict[str, Any]]:
        """Downloads the full catalog and returns only entries added within the lookback window."""
        body = await http.get_json(
            str(self.config.feed_url),
            check_robots=False,  # documented public data feed, not a crawled website
            correlation_id=correlation_id,
        )
        vulnerabilities = body.get("vulnerabilities") if isinstance(body, dict) else None
        if not isinstance(vulnerabilities, list):
            raise SourceFormatError("KEV feed has no 'vulnerabilities' list")

        cutoff = datetime.now(timezone.utc).date() - timedelta(days=self.config.lookback_days)
        return [record for record in vulnerabilities if _is_recent_or_unparseable(record, cutoff)]

    def parse_record(self, record: dict[str, Any], collected_at: datetime) -> Advisory:
        """Maps one KEV entry to an Advisory."""
        cve_id = record["cveID"]
        due_date = record.get("dueDate")

        return Advisory(
            item_id=build_item_id(self.source_name, cve_id),
            source_name=self.source_name,
            external_id=cve_id,
            title=record["vulnerabilityName"],
            url=NVD_CVE_URL_TEMPLATE.format(cve_id=cve_id),
            content=truncate_content(record.get("shortDescription")),
            tags=[cwe for cwe in record.get("cwes", []) if isinstance(cwe, str) and cwe],
            published_at=datetime.combine(_parse_date(record["dateAdded"]), time.min, tzinfo=timezone.utc),
            collected_at=collected_at,
            raw_payload=to_json_safe(record),
            cve_id=cve_id,
            vendor=record.get("vendorProject") or None,
            product=record.get("product") or None,
            ecosystem=None,  # KEV covers commercial products as well as packages; no ecosystem field
            severity=None,   # KEV does not rate severity
            known_exploited=True,  # every KEV entry is exploited in the wild by definition
            known_ransomware_use=RANSOMWARE_USE_VALUES.get(record.get("knownRansomwareCampaignUse")),
            remediation_due_date=_parse_date(due_date) if due_date else None,
        )


def _parse_date(value: Any) -> date:
    """KEV dates are 'YYYY-MM-DD' strings. Raises ValueError/TypeError otherwise (the record is then skipped)."""
    return date.fromisoformat(value)


def _is_recent_or_unparseable(record: Any, cutoff: date) -> bool:
    """
    Keeps entries added on or after `cutoff`.
    Entries with a missing or malformed dateAdded are kept so parse_record rejects
    them and they show up in skipped_count, instead of disappearing silently.
    """
    try:
        return _parse_date(record["dateAdded"]) >= cutoff
    except (KeyError, TypeError, ValueError):
        return True
