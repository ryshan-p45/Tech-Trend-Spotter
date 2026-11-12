import calendar
import time
from datetime import datetime, timezone
from typing import Any

import feedparser

from functionality.data_collection.collectors.base import (
    BaseCollector, SourceFormatError, to_json_safe, truncate_content,
)
from functionality.data_collection.http_client import SourceHttpClient
from interfaces.collection_interfaces import WebArticle, build_item_id
from interfaces.source_config_interfaces import RssFeedConfig

"""
RSS / Atom feed collector (web source).

One instance = one feed. Feeds to collect are listed explicitly in
sources.yaml (web.rss_feeds), which acts as an allowlist - URLs never come
from user input.

We download the feed ourselves through SourceHttpClient (so we get timeouts,
retries and robots.txt checks) and only use feedparser to parse the bytes.
feedparser also sanitises HTML in summaries, removing scripts and unsafe markup.
"""


class RssFeedCollector(BaseCollector):
    """Collects entries from a single RSS or Atom feed."""

    source_type = "web"

    def __init__(self, config: RssFeedConfig):
        # Config is validated by the pydantic model (slug key, https URL)
        # key is a short stable slug, e.g. "krebsonsecurity" -> source_name "rss:krebsonsecurity"
        self.source_name = f"rss:{config.key}"
        self.feed_url = str(config.url)
        self.site_name = config.site_name

    async def fetch_records(self, http: SourceHttpClient, correlation_id: str) -> list[dict[str, Any]]:
        """Downloads and parses the feed; returns its entries."""
        raw_feed = await http.get_bytes(self.feed_url, check_robots=True, correlation_id=correlation_id)
        parsed = feedparser.parse(raw_feed)

        # 'bozo' means the feed was malformed; feedparser may still recover entries, so only fail if it found none
        if parsed.bozo and not parsed.entries:
            raise SourceFormatError(f"Feed {self.feed_url} could not be parsed: {parsed.get('bozo_exception')}")
        return list(parsed.entries)

    def parse_record(self, record: dict[str, Any], collected_at: datetime) -> WebArticle:
        """Maps one feed entry to a WebArticle."""
        link = record.get("link") or None
        # Prefer the feed's own GUID; fall back to the link so we always have a stable ID
        external_id = record.get("id") or link
        if not external_id:
            raise ValueError("Feed entry has neither an id nor a link")

        return WebArticle(
            item_id=build_item_id(self.source_name, external_id),
            source_name=self.source_name,
            external_id=external_id,
            title=record["title"],
            url=link,
            content=truncate_content(record.get("summary")),
            tags=[tag["term"] for tag in record.get("tags", []) if tag.get("term")],
            published_at=_entry_published_at(record),
            collected_at=collected_at,
            raw_payload=to_json_safe(record),
            site_name=self.site_name,
        )


def _entry_published_at(record: dict[str, Any]) -> datetime | None:
    """feedparser gives dates as UTC time.struct_time; convert to an aware datetime. Falls back to 'updated'."""
    parsed_time: time.struct_time | None = record.get("published_parsed") or record.get("updated_parsed")
    if parsed_time is None:
        return None
    return datetime.fromtimestamp(calendar.timegm(parsed_time), tz=timezone.utc)
