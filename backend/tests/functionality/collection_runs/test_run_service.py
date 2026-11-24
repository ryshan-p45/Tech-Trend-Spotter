import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from functionality.collection_runs.run_service import CollectionRunService, RunCooldownError
from functionality.data_collection.http_client import FetchError
from functionality.storage.runs_repository import RunAlreadyActiveError
from tests.fakes import FakeItemsStore, FakeRunsStore, StaticCollector, make_run

"""Tests for starting and executing collection runs, with in-memory stores and fake collectors."""


NOW = datetime.now(timezone.utc)


def make_service(runs=None, collectors=None, build_error=None, cooldown_seconds=300):
    def build_collectors():
        if build_error:
            raise build_error
        return collectors or []
    runs_store, items_store = runs or FakeRunsStore(), FakeItemsStore()
    service = CollectionRunService(runs=runs_store, items=items_store,
                                   build_collectors=build_collectors, cooldown_seconds=cooldown_seconds)
    return service, runs_store, items_store


@pytest.fixture(autouse=True)
def no_real_http(monkeypatch):
    """Collectors in these tests never use HTTP, but make sure no real client is created either."""
    monkeypatch.setattr("functionality.data_collection.collection_core.build_http_client",
                        lambda: httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))))


def test_first_run_is_queued():
    service, runs, _ = make_service()
    run = service.request_run()
    assert run.status == "queued"
    assert runs.get_run(run.run_id) is not None


@pytest.mark.parametrize("status", ["queued", "running"])
def test_rejects_run_while_another_is_active(status):
    service, _, _ = make_service(runs=FakeRunsStore([make_run("r1", status, NOW - timedelta(hours=1))]))
    with pytest.raises(RunAlreadyActiveError):
        service.request_run()


def test_rejects_run_within_cooldown_with_retry_after():
    service, _, _ = make_service(runs=FakeRunsStore([make_run("r1", "completed", NOW - timedelta(seconds=100))]))
    with pytest.raises(RunCooldownError) as error:
        service.request_run()
    assert 195 <= error.value.retry_after_seconds <= 201


def test_allows_run_after_cooldown():
    service, _, _ = make_service(runs=FakeRunsStore([make_run("r1", "completed", NOW - timedelta(seconds=301))]))
    assert service.request_run().status == "queued"


def test_execute_run_saves_items_and_records_each_source():
    collectors = [
        StaticCollector("rss:a", ["one", "two"]),
        StaticCollector("rss:b", [], error=FetchError("down", retryable=True)),
    ]
    service, runs, items = make_service(collectors=collectors)
    run = service.request_run()

    asyncio.run(service.execute_run(run.run_id))

    finished = runs.get_run(run.run_id)
    assert finished.status == "completed"  # one failing source doesn't fail the whole run
    assert finished.items_collected == 2
    assert finished.items_new == 2
    assert finished.started_at is not None and finished.finished_at is not None
    assert {(s.source_name, s.status) for s in finished.sources} == {("rss:a", "success"), ("rss:b", "failed")}
    assert len(items.items) == 2


def test_items_seen_before_are_not_counted_as_new():
    service, runs, _ = make_service(collectors=[StaticCollector("rss:a", ["one"])], cooldown_seconds=0)
    first = service.request_run()
    asyncio.run(service.execute_run(first.run_id))
    second = service.request_run()
    asyncio.run(service.execute_run(second.run_id))

    assert runs.get_run(second.run_id).items_new == 0


def test_execute_run_records_failure_without_leaking_details():
    service, runs, _ = make_service(build_error=RuntimeError("secret internal detail"))
    run = service.request_run()

    asyncio.run(service.execute_run(run.run_id))

    failed = runs.get_run(run.run_id)
    assert failed.status == "failed"
    assert "secret internal detail" not in failed.error_message
    assert "start a new run" in failed.error_message
