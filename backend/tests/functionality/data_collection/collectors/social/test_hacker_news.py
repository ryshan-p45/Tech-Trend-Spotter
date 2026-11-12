import asyncio

import httpx
import pytest
from pydantic import ValidationError

from functionality.data_collection.collectors.social.hacker_news import HackerNewsCollector
from functionality.data_collection.http_client import SourceHttpClient
from interfaces.source_config_interfaces import HackerNewsConfig

"""Tests for the Hacker News collector using a fixed, recorded-style Algolia response."""


CONFIG = HackerNewsConfig(
    search_url="https://hn.test/api/v1/search_by_date",
    item_url_template="https://news.test/item?id={item_id}",
)

VALID_HIT = {
    "objectID": "4242",
    "title": "New RCE found in popular library",
    "url": "https://example.com/rce",
    "points": 321,
    "num_comments": 87,
    "created_at": "2026-11-10T08:30:00Z",
    "author": "someone",
    "_tags": ["story", "author_someone", "story_4242", "front_page"],
}


def run_collector(body, status=200):
    """Runs the collector against a mocked Algolia API that returns `body`."""
    transport = httpx.MockTransport(lambda request: httpx.Response(status, json=body))
    http = SourceHttpClient(httpx.AsyncClient(transport=transport), max_attempts=1, backoff_base_seconds=0)
    return asyncio.run(HackerNewsCollector(CONFIG).collect(http, correlation_id="test"))


def test_parses_valid_hit_into_social_post():
    result = run_collector({"hits": [VALID_HIT]})

    assert result.status == "success"
    assert result.source_type == "social"
    post = result.items[0]
    assert post.title == VALID_HIT["title"]
    assert post.score == 321
    assert post.comment_count == 87
    assert str(post.discussion_url) == "https://news.test/item?id=4242"
    assert post.tags == ["story", "front_page"]
    assert post.published_at.tzinfo is not None


def test_author_is_not_kept_in_raw_payload():
    post = run_collector({"hits": [VALID_HIT]}).items[0]
    assert "author" not in post.raw_payload


def test_ask_hn_without_url_is_kept_with_null_url():
    hit = {**VALID_HIT, "url": None, "story_text": "What are you using for X?"}
    post = run_collector({"hits": [hit]}).items[0]
    assert post.url is None
    assert post.content == "What are you using for X?"


def test_invalid_hits_are_skipped_not_fatal():
    missing_title = {k: v for k, v in VALID_HIT.items() if k != "title"}
    result = run_collector({"hits": [VALID_HIT, missing_title]})
    assert result.status == "success"
    assert len(result.items) == 1
    assert result.skipped_count == 1


def test_unexpected_response_shape_fails_as_non_retryable():
    result = run_collector({"unexpected": True})
    assert result.status == "failed"
    assert result.items == []
    assert result.error.category == "non_retryable"


def test_server_error_fails_as_retryable():
    result = run_collector({}, status=503)
    assert result.status == "failed"
    assert result.error.category == "retryable"


def test_uses_configured_url_and_thresholds():
    seen = []

    def handler(request):
        seen.append(request.url)
        return httpx.Response(200, json={"hits": []})

    http = SourceHttpClient(httpx.AsyncClient(transport=httpx.MockTransport(handler)), max_attempts=1)
    config = CONFIG.model_copy(update={"min_points": 10, "max_items": 5})
    asyncio.run(HackerNewsCollector(config).collect(http, correlation_id="test"))

    assert seen[0].host == "hn.test"
    assert seen[0].params["numericFilters"] == "points>=10"
    assert seen[0].params["hitsPerPage"] == "5"


@pytest.mark.parametrize("override", [
    {"max_items": 0},
    {"min_points": -1},
    {"search_url": "http://hn.test/api"},
    {"item_url_template": "https://news.test/item"},
])
def test_rejects_invalid_config(override):
    with pytest.raises(ValidationError):
        HackerNewsConfig(**{**CONFIG.model_dump(mode="json"), **override})
