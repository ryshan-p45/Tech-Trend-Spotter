import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from database.connection import DatabaseUnavailableError
from endpoints.dependencies import get_items_repository, get_run_service, get_runs_repository
from functionality.collection_runs.run_service import CollectionRunService
from functionality.storage.items_repository import InvalidCursorError
from interfaces.api_interfaces import DailyCount, ItemResponse, ItemStatsResponse, SeverityCounts
from main import app
from tests.fakes import FakeItemsStore, FakeRunsStore, StaticCollector, make_run

"""
API tests: status codes, envelopes and error mapping. Repositories are replaced
with fakes through FastAPI dependency overrides - no database or network.
"""


NOW = datetime.now(timezone.utc)

ITEM = ItemResponse(
    item_id="a" * 64, source_type="advisory", source_name="cisa_kev", title="Example vuln", url=None,
    summary="Short summary", tags=["CWE-79"], published_at=NOW, first_collected_at=NOW,
    site_name=None, score=None, comment_count=None, discussion_url=None, cve_id="CVE-2026-1234",
    affected=[{"vendor": "Acme", "product": "Widget", "ecosystem": None}], severity=None,
    known_exploited=True, known_ransomware_use=False, remediation_due_date=date(2026, 12, 1),
)


class FakeItemsReader:
    """Stands in for ItemsRepository's read methods; records the arguments it was called with."""

    def __init__(self, error: Exception | None = None):
        self.error = error
        self.calls = []

    def list_items(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return [ITEM], "next-page-cursor"

    def get_stats(self, days):
        if self.error:
            raise self.error
        return ItemStatsResponse(
            days=days, total_items=1, by_source_type={"web": 0, "social": 0, "advisory": 1}, by_source=[],
            daily_counts=[DailyCount(date=NOW.date(), web=0, social=0, advisory=1)],
            advisory_severity=SeverityCounts(critical=0, high=0, medium=0, low=0, unrated=1),
            known_exploited=1, top_vendors=[], top_ecosystems=[],
        )


@pytest.fixture
def client():
    yield TestClient(app)  # no `with`: skips the lifespan, so no database connection is attempted
    app.dependency_overrides.clear()


def use_items(reader):
    app.dependency_overrides[get_items_repository] = lambda: reader


def use_runs(store, collectors=None):
    app.dependency_overrides[get_runs_repository] = lambda: store
    app.dependency_overrides[get_run_service] = lambda: CollectionRunService(
        runs=store, items=FakeItemsStore(), build_collectors=lambda: collectors or [], cooldown_seconds=300)


# ---------- Health ----------

def test_health_uses_data_envelope(client):
    assert client.get("/v1/health").json() == {"data": {"status": "ok"}}


# ---------- Items ----------

def test_list_items_returns_page_envelope(client):
    reader = FakeItemsReader()
    use_items(reader)
    body = client.get("/v1/items", params={"source_type": "advisory", "limit": 10}).json()

    assert body["data"][0]["cve_id"] == "CVE-2026-1234"
    assert body["data"][0]["score"] is None  # same shape for every item type
    assert body["pagination"] == {"next_cursor": "next-page-cursor", "limit": 10}
    assert reader.calls[0] == {"source_type": "advisory", "source_name": None, "limit": 10, "cursor": None}


@pytest.mark.parametrize("params", [
    {"limit": 0}, {"limit": 101}, {"source_type": "video"}, {"source_name": "DROP TABLE"}, {"cursor": "x" * 501},
])
def test_list_items_rejects_invalid_params(client, params):
    use_items(FakeItemsReader())
    response = client.get("/v1/items", params=params)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_list_items_bad_cursor_is_400(client):
    use_items(FakeItemsReader(error=InvalidCursorError("bad")))
    response = client.get("/v1/items", params={"cursor": "garbage"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_cursor"


def test_database_down_is_503_with_readable_message(client):
    use_items(FakeItemsReader(error=DatabaseUnavailableError("connection refused to db-host")))
    response = client.get("/v1/items")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "database_unavailable"
    assert "db-host" not in response.json()["error"]["message"]


def test_unexpected_error_is_500_without_details():
    use_items(FakeItemsReader(error=RuntimeError("internal secret")))
    response = TestClient(app, raise_server_exceptions=False).get("/v1/items")
    app.dependency_overrides.clear()
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "internal secret" not in response.text


def test_item_stats(client):
    use_items(FakeItemsReader())
    body = client.get("/v1/item-stats", params={"days": 7}).json()
    assert body["data"]["days"] == 7
    assert body["data"]["known_exploited"] == 1


@pytest.mark.parametrize("days", [0, 91])
def test_item_stats_rejects_out_of_range_days(client, days):
    use_items(FakeItemsReader())
    assert client.get("/v1/item-stats", params={"days": days}).status_code == 400


# ---------- Collection runs ----------

def test_start_run_returns_202_and_runs_in_background(client):
    store = FakeRunsStore()
    use_runs(store, collectors=[StaticCollector("rss:a", ["one", "two"])])

    response = client.post("/v1/collection-runs")

    assert response.status_code == 202
    run_id = response.json()["data"]["run_id"]
    assert response.json()["data"]["status"] == "queued"
    # TestClient runs background tasks before returning, so the run has finished here
    finished = client.get(f"/v1/collection-runs/{run_id}").json()["data"]
    assert finished["status"] == "completed"
    assert finished["items_collected"] == 2


def test_start_run_while_active_is_409(client):
    use_runs(FakeRunsStore([make_run(str(uuid.uuid4()), "running", NOW)]))
    response = client.post("/v1/collection-runs")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "run_in_progress"


def test_start_run_during_cooldown_is_429_with_retry_after(client):
    use_runs(FakeRunsStore([make_run(str(uuid.uuid4()), "completed", NOW - timedelta(seconds=60))]))
    response = client.post("/v1/collection-runs")
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "run_cooldown"
    assert 200 <= int(response.headers["Retry-After"]) <= 241


def test_latest_run(client):
    store = FakeRunsStore([make_run(str(uuid.uuid4()), "completed", NOW - timedelta(hours=2)),
                           make_run("newest-id", "completed", NOW - timedelta(hours=1))])
    use_runs(store)
    assert client.get("/v1/collection-runs/latest").json()["data"]["run_id"] == "newest-id"


def test_latest_run_when_none_is_404(client):
    use_runs(FakeRunsStore())
    response = client.get("/v1/collection-runs/latest")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "no_runs"


def test_unknown_run_is_404(client):
    use_runs(FakeRunsStore())
    response = client.get(f"/v1/collection-runs/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "run_not_found"


def test_malformed_run_id_is_400(client):
    use_runs(FakeRunsStore())
    assert client.get("/v1/collection-runs/not-a-uuid").status_code == 400


def test_unknown_route_uses_error_envelope(client):
    response = client.get("/v1/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
