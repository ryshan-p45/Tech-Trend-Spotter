from datetime import datetime
from typing import Any

from functionality.data_collection.collectors.base import (
    BaseCollector, SourceFormatError, to_json_safe, truncate_content,
)
from functionality.data_collection.http_client import SourceHttpClient
from interfaces.collection_interfaces import SocialPost, build_item_id
from interfaces.source_config_interfaces import HackerNewsConfig

"""
Hacker News collector (social source).

Uses the free, key-less Algolia Hacker News Search API:
    https://hn.algolia.com/api
One request returns the most recent stories above a points threshold, with
title, link, points and comment count - so we don't need one call per story.

URLs and thresholds come from sources.yaml (social.hacker_news), already
validated by HackerNewsConfig.
"""


# Algolia tags worth keeping as item tags (others are author_/story_ IDs we don't need)
KEPT_TAGS = {"story", "ask_hn", "show_hn", "front_page", "poll"}

# Fields removed from raw_payload: usernames are personal data we don't need for trend analysis
DROPPED_PAYLOAD_FIELDS = {"author", "_highlightResult", "children"}


class HackerNewsCollector(BaseCollector):
    """Collects recent, popular Hacker News stories."""

    source_name = "hacker_news"
    source_type = "social"

    def __init__(self, config: HackerNewsConfig):
        # Config is validated by the pydantic model (https URLs, 1-100 items, etc.)
        self.config = config

    async def fetch_records(self, http: SourceHttpClient, correlation_id: str) -> list[dict[str, Any]]:
        """One API call; returns the list of story 'hits'."""
        body = await http.get_json(
            str(self.config.search_url),
            params={
                "tags": "story",
                "numericFilters": f"points>={self.config.min_points}",
                "hitsPerPage": self.config.max_items,
            },
            check_robots=False,  # documented public API, not a crawled website
            correlation_id=correlation_id,
        )
        hits = body.get("hits") if isinstance(body, dict) else None
        if not isinstance(hits, list):
            raise SourceFormatError("Algolia response has no 'hits' list")
        return hits

    def parse_record(self, record: dict[str, Any], collected_at: datetime) -> SocialPost:
        """Maps one Algolia hit to a SocialPost."""
        external_id = str(record["objectID"])
        created_at = record.get("created_at")

        return SocialPost(
            item_id=build_item_id(self.source_name, external_id),
            source_name=self.source_name,
            external_id=external_id,
            title=record["title"],
            url=record.get("url") or None,  # Ask HN posts have no external link
            content=truncate_content(record.get("story_text")),
            tags=[tag for tag in record.get("_tags", []) if tag in KEPT_TAGS],
            published_at=datetime.fromisoformat(created_at) if created_at else None,
            collected_at=collected_at,
            raw_payload=to_json_safe({k: v for k, v in record.items() if k not in DROPPED_PAYLOAD_FIELDS}),
            score=record.get("points"),
            comment_count=record.get("num_comments"),
            discussion_url=self.config.item_url_template.format(item_id=external_id),
        )
