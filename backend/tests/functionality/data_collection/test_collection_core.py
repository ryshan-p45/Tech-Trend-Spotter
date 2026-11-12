import asyncio
from datetime import datetime
from typing import Any

import httpx

from functionality.data_collection.collection_core import run_collection
from functionality.data_collection.collectors.base import BaseCollector
from functionality.data_collection.http_client import FetchError, SourceHttpClient
from interfaces.collection_interfaces import SocialPost, build_item_id

"""Tests for the orchestrator: collectors run independently and failures stay isolated."""


class StubSocialCollector(BaseCollector):
    """Minimal collector returning one fixed record, or raising/hanging when asked to."""

    source_type = "social"

    def __init__(self, name: str, behaviour: str = "ok"):
        self.source_name = name
        self.behaviour = behaviour
        self.run_timeout_seconds = 0.05

    async def fetch_records(self, http: SourceHttpClient, correlation_id: str) -> list[dict[str, Any]]:
        if self.behaviour == "fail":
            raise FetchError("source down", retryable=True)
        if self.behaviour == "hang":
            await asyncio.sleep(10)
        if self.behaviour == "bug":
            raise RuntimeError("unexpected bug")
        return [{"id": "1", "title": "Hello"}]

    def parse_record(self, record: dict[str, Any], collected_at: datetime) -> SocialPost:
        return SocialPost(
            item_id=build_item_id(self.source_name, record["id"]), source_name=self.source_name,
            external_id=record["id"], title=record["title"], url=None, content=None,
            published_at=None, collected_at=collected_at, raw_payload=record,
            score=None, comment_count=None, discussion_url=None,
        )


def run(collectors):
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200)))
    return asyncio.run(run_collection(collectors, correlation_id="run-1", client=client))


def test_failures_do_not_affect_other_collectors():
    results = run([
        StubSocialCollector("good"),
        StubSocialCollector("down", behaviour="fail"),
        StubSocialCollector("buggy", behaviour="bug"),
    ])
    by_name = {result.source_name: result for result in results}

    assert by_name["good"].status == "success" and len(by_name["good"].items) == 1
    assert by_name["down"].status == "failed" and by_name["down"].error.category == "retryable"
    assert by_name["buggy"].status == "failed" and by_name["buggy"].error.category == "non_retryable"


def test_hanging_collector_is_stopped_by_timeout():
    result = run([StubSocialCollector("slow", behaviour="hang")])[0]
    assert result.status == "failed"
    assert result.error.category == "retryable"


def test_correlation_id_is_shared_across_results():
    results = run([StubSocialCollector("a"), StubSocialCollector("b")])
    assert {result.correlation_id for result in results} == {"run-1"}
