from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit

from app_logging import get_logger
from functionality.data_collection.collectors.base import (
    BaseCollector, SourceFormatError, to_json_safe, truncate_content,
)
from functionality.data_collection.http_client import SourceHttpClient
from interfaces.collection_interfaces import AffectedProduct, Advisory, Severity, build_item_id
from interfaces.source_config_interfaces import GitHubAdvisoriesConfig

"""
GitHub Security Advisories collector (advisory source).

Uses the GitHub global advisory database REST API (free, public):
    https://docs.github.com/en/rest/security-advisories/global-advisories
We collect only GitHub-reviewed advisories (curated, with ecosystem and
package names), which name the affected open-source packages - a strong
signal for which technologies and companies are affected by a trend.

Rate limits: 60 requests/hour without a token, 5,000 with one. The token is
optional and comes from the GITHUB_TOKEN environment variable (never from
sources.yaml). A token with no permissions is enough because the data is public.

Pagination: ~100 advisories cover only a few days, so we follow the
`Link: rel="next"` header page by page, up to `max_pages` per run.

Notes on mapping:
    - One advisory = one item; every affected package is listed in `affected`.
    - Withdrawn advisories are dropped (GitHub retracted them as invalid).
    - `credits` (GitHub usernames of reporters) is personal data and is
      removed from raw_payload.
"""


logger = get_logger("data_collection.github_advisories")

# Advisories per page (GitHub's maximum)
PAGE_SIZE = 100

# GitHub's REST API version this collector was written against
GITHUB_API_VERSION = "2022-11-28"

# Advisory title limit from the CollectedItem schema; longer summaries are cut rather than rejected
MAX_TITLE_LENGTH = 500

# GitHub severities -> our normalised levels ('unknown' and anything new become null)
SEVERITY_MAP: dict[str, Severity] = {"low": "low", "medium": "medium", "high": "high", "critical": "critical"}

# Fields removed from raw_payload: reporter usernames are personal data we don't need
DROPPED_PAYLOAD_FIELDS = {"credits"}


class GitHubAdvisoriesCollector(BaseCollector):
    """Collects recently published, GitHub-reviewed security advisories."""

    source_name = "github_advisories"
    source_type = "advisory"

    def __init__(self, config: GitHubAdvisoriesConfig, api_token: str | None = None):
        # Config is validated by the pydantic model (https URL, lookback and page ranges)
        # api_token is optional and only ever sent in the Authorization header - never logged
        self.config = config
        self.api_token = api_token or None

    async def fetch_records(self, http: SourceHttpClient, correlation_id: str) -> list[dict[str, Any]]:
        """Fetches pages of advisories until there are no more, or max_pages is reached."""
        url: str | None = str(self.config.api_url)
        params: dict[str, Any] | None = self._first_page_params()
        records: list[dict[str, Any]] = []
        pages_fetched = 0

        while url is not None and pages_fetched < self.config.max_pages:
            page = await http.get_json_page(url, params=params, headers=self._request_headers(),
                                            check_robots=False,  # documented public API
                                            correlation_id=correlation_id)
            if not isinstance(page.body, list):
                raise SourceFormatError("GitHub advisories response is not a list")
            records.extend(page.body)
            pages_fetched += 1
            # The next-page URL already contains every query parameter
            url, params = self._validated_next_url(page.next_url), None

        if url is not None:
            logger.warning("Page limit reached; older advisories in the lookback window were not collected", extra={
                "correlation_id": correlation_id,
                "context": {"source_name": self.source_name, "max_pages": self.config.max_pages},
            })

        return [record for record in records if not _is_withdrawn(record)]

    def parse_record(self, record: dict[str, Any], collected_at: datetime) -> Advisory:
        """Maps one GitHub advisory to an Advisory."""
        ghsa_id = record["ghsa_id"]

        return Advisory(
            item_id=build_item_id(self.source_name, ghsa_id),
            source_name=self.source_name,
            external_id=ghsa_id,
            title=record["summary"][:MAX_TITLE_LENGTH],
            url=record.get("html_url") or None,
            content=truncate_content(record.get("description")),
            tags=[cwe["cwe_id"] for cwe in record.get("cwes") or [] if cwe.get("cwe_id")],
            published_at=datetime.fromisoformat(record["published_at"]),
            collected_at=collected_at,
            raw_payload=to_json_safe({k: v for k, v in record.items() if k not in DROPPED_PAYLOAD_FIELDS}),
            cve_id=record.get("cve_id") or None,
            affected=_affected_packages(record),
            severity=SEVERITY_MAP.get(record.get("severity")),
            known_exploited=False,      # GitHub advisories don't report exploitation (CISA KEV does)
            known_ransomware_use=None,  # not reported by GitHub
            remediation_due_date=None,  # not reported by GitHub
        )

    # ---------- Helpers ----------

    def _first_page_params(self) -> dict[str, Any]:
        """Query for the first page: reviewed advisories published since the lookback cutoff, newest first."""
        cutoff = datetime.now(timezone.utc).date() - timedelta(days=self.config.lookback_days)
        return {
            "type": "reviewed",
            "published": f">={cutoff.isoformat()}",
            "sort": "published",
            "direction": "desc",
            "per_page": PAGE_SIZE,
        }

    def _request_headers(self) -> dict[str, str]:
        """GitHub's recommended headers, plus the token when one is configured."""
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": GITHUB_API_VERSION}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        return headers

    def _validated_next_url(self, next_url: str | None) -> str | None:
        """
        The next-page URL comes from a response header, so it is untrusted: only follow it
        if it points to the same https host as the configured API (our token must never
        be sent anywhere else).
        """
        if next_url is None:
            return None
        configured = urlsplit(str(self.config.api_url))
        candidate = urlsplit(next_url)
        if candidate.scheme != "https" or candidate.netloc != configured.netloc:
            raise SourceFormatError(f"Next-page link points to an unexpected host: {candidate.netloc}")
        return next_url


def _is_withdrawn(record: Any) -> bool:
    """Withdrawn advisories were retracted by GitHub and should not count as signals."""
    return isinstance(record, dict) and bool(record.get("withdrawn_at"))


def _affected_packages(record: dict[str, Any]) -> list[AffectedProduct]:
    """
    One AffectedProduct per vulnerable package, in the order GitHub lists them.
    - GitHub repeats a package once per vulnerable version range, so duplicates are removed
      (version ranges stay in raw_payload).
    - Packages without a name are left out.
    - Open-source packages have no single vendor, so vendor is null.
    """
    affected: list[AffectedProduct] = []
    for vulnerability in record.get("vulnerabilities") or []:
        package = vulnerability.get("package") or {}
        if not package.get("name"):
            continue
        product = AffectedProduct(vendor=None, product=package["name"], ecosystem=package.get("ecosystem") or None)
        if product not in affected:
            affected.append(product)
    return affected
