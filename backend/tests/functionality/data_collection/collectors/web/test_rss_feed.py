import asyncio

import httpx
import pytest
from pydantic import ValidationError

from functionality.data_collection.collectors.web.rss_feed import RssFeedCollector
from functionality.data_collection.http_client import SourceHttpClient
from interfaces.collection_interfaces import MAX_CONTENT_LENGTH
from interfaces.source_config_interfaces import RssFeedConfig

"""Tests for the RSS/Atom collector using a fixed sample feed."""


SAMPLE_RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <title>Example Security Blog</title>
  <item>
    <title>Critical flaw in FooLib</title>
    <link>https://blog.test/foolib-flaw</link>
    <guid>https://blog.test/?p=1</guid>
    <pubDate>Tue, 10 Nov 2026 08:30:00 GMT</pubDate>
    <category>Vulnerabilities</category>
    <description><![CDATA[<p>Summary text</p><script>alert(1)</script>]]></description>
  </item>
  <item>
    <link>https://blog.test/no-title</link>
  </item>
</channel></rss>"""


def run_collector(feed_body: str, feed_status: int = 200):
    """Runs the collector against a mocked site that serves robots.txt (404) and the feed."""
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(feed_status, text=feed_body)

    http = SourceHttpClient(httpx.AsyncClient(transport=httpx.MockTransport(handler)),
                            max_attempts=1, backoff_base_seconds=0)
    collector = RssFeedCollector(RssFeedConfig(key="example", url="https://blog.test/feed", site_name="Example"))
    return asyncio.run(collector.collect(http, correlation_id="test"))


def test_parses_feed_entries_into_web_articles():
    result = run_collector(SAMPLE_RSS)

    assert result.status == "success"
    assert result.source_type == "web"
    assert result.source_name == "rss:example"
    article = result.items[0]
    assert article.title == "Critical flaw in FooLib"
    assert str(article.url) == "https://blog.test/foolib-flaw"
    assert article.external_id == "https://blog.test/?p=1"
    assert article.tags == ["Vulnerabilities"]
    assert article.published_at.isoformat() == "2026-11-10T08:30:00+00:00"
    assert article.site_name == "Example"


def test_feed_html_is_sanitised():
    article = run_collector(SAMPLE_RSS).items[0]
    assert "<script>" not in article.content


def test_entry_without_title_is_skipped():
    result = run_collector(SAMPLE_RSS)
    assert len(result.items) == 1
    assert result.skipped_count == 1


def test_same_entry_gets_same_item_id_across_runs():
    assert run_collector(SAMPLE_RSS).items[0].item_id == run_collector(SAMPLE_RSS).items[0].item_id


def test_long_content_is_truncated_not_rejected():
    long_feed = SAMPLE_RSS.replace("<p>Summary text</p>", "a" * (MAX_CONTENT_LENGTH + 500))
    article = run_collector(long_feed).items[0]
    assert len(article.content) == MAX_CONTENT_LENGTH


def test_unparseable_feed_fails_as_non_retryable():
    result = run_collector("this is not a feed <<<")
    assert result.status == "failed"
    assert result.error.category == "non_retryable"


def test_rejects_non_https_feed_url():
    with pytest.raises(ValidationError):
        RssFeedConfig(key="bad", url="http://blog.test/feed", site_name="Bad")


def test_rejects_invalid_feed_key():
    with pytest.raises(ValidationError):
        RssFeedConfig(key="Not A Slug!", url="https://blog.test/feed", site_name="Bad")
