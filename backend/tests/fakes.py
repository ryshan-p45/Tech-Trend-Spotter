from datetime import datetime, timezone
from typing import Any

from functionality.data_collection.collectors.base import BaseCollector
from functionality.data_collection.http_client import SourceHttpClient
from interfaces.api_interfaces import CollectionRunResponse, RunSourceResult
from interfaces.collection_interfaces import CollectedItem, WebArticle, build_item_id

"""
In-memory stand-ins for the repositories and collectors, shared by the service
and endpoint tests. No database or network is touched.
"""


class FakeRunsStore:
    """Keeps runs in a dict, newest first on list. Mirrors RunsRepository's behaviour."""

    def __init__(self, runs: list[CollectionRunResponse] | None = None):
        self.runs: dict[str, CollectionRunResponse] = {run.run_id: run for run in runs or []}

    def create_run(self, run_id: str, requested_at: datetime) -> CollectionRunResponse:
        run = CollectionRunResponse(run_id=run_id, status="queued", requested_at=requested_at, started_at=None,
                                    finished_at=None, items_collected=0, items_new=0, sources=[], error_message=None)
        self.runs[run_id] = run
        return run

    def mark_running(self, run_id: str, started_at: datetime) -> None:
        self.runs[run_id] = self.runs[run_id].model_copy(update={"status": "running", "started_at": started_at})

    def finish_run(self, run_id: str, *, status, finished_at, items_collected, items_new, sources, error_message) -> None:
        self.runs[run_id] = self.runs[run_id].model_copy(update={
            "status": status, "finished_at": finished_at, "items_collected": items_collected,
            "items_new": items_new, "sources": sources, "error_message": error_message,
        })

    def get_run(self, run_id: str) -> CollectionRunResponse | None:
        return self.runs.get(run_id)

    def list_runs(self, limit: int) -> list[CollectionRunResponse]:
        return sorted(self.runs.values(), key=lambda run: run.requested_at, reverse=True)[:limit]


class FakeItemsStore:
    """Remembers saved items; an item is 'new' the first time its item_id is seen."""

    def __init__(self):
        self.items: dict[str, CollectedItem] = {}

    def upsert_items(self, items: list[CollectedItem]) -> int:
        new_count = sum(1 for item in {i.item_id: i for i in items} if item not in self.items)
        self.items.update({item.item_id: item for item in items})
        return new_count


class StaticCollector(BaseCollector):
    """Returns a fixed list of article titles, or fails with `error` when given."""

    source_type = "web"

    def __init__(self, source_name: str, titles: list[str], error: Exception | None = None):
        self.source_name = source_name
        self.titles = titles
        self.error = error

    async def fetch_records(self, http: SourceHttpClient, correlation_id: str) -> list[dict[str, Any]]:
        if self.error:
            raise self.error
        return [{"title": title} for title in self.titles]

    def parse_record(self, record: dict[str, Any], collected_at: datetime) -> WebArticle:
        return make_article(self.source_name, record["title"], collected_at)


def make_article(source_name: str, title: str, collected_at: datetime | None = None) -> WebArticle:
    return WebArticle(
        item_id=build_item_id(source_name, title), source_name=source_name, external_id=title, title=title,
        url="https://example.test/" + title.replace(" ", "-"), content=f"<p>About {title}</p>", tags=["news"],
        published_at=datetime(2026, 11, 20, 9, 0, tzinfo=timezone.utc),
        collected_at=collected_at or datetime.now(timezone.utc), raw_payload={"title": title}, site_name="Example",
    )


def make_run(run_id: str, status: str, requested_at: datetime) -> CollectionRunResponse:
    finished = status in ("completed", "failed")
    return CollectionRunResponse(
        run_id=run_id, status=status, requested_at=requested_at, started_at=requested_at,
        finished_at=requested_at if finished else None, items_collected=3 if finished else 0, items_new=1 if finished else 0,
        sources=[RunSourceResult(source_name="rss:a", source_type="web", status="success", items=3, skipped=0,
                                 error_message=None)] if finished else [],
        error_message=None,
    )
