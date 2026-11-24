import os
import uuid
from datetime import datetime, timedelta, timezone

import psycopg2
import pytest

from database.connection import Database
from database.migrate import migrate
from functionality.storage.items_repository import ItemsRepository
from functionality.storage.runs_repository import RunAlreadyActiveError, RunsRepository
from interfaces.api_interfaces import RunSourceResult
from interfaces.collection_interfaces import Advisory, AffectedProduct, build_item_id
from tests.fakes import make_article

"""
Integration tests for the SQL in the repositories and the migration.

Skipped unless TEST_DATABASE_URL is set, e.g.:
    TEST_DATABASE_URL=postgresql://user:pass@localhost:5432/techtrendspotter pytest tests/database

Safe to point at a development database: each test run creates its own
throwaway schema, migrates it, and drops it afterwards. Real tables are never touched.
"""


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set")

NOW = datetime.now(timezone.utc)


@pytest.fixture
def database():
    schema = f"tts_test_{uuid.uuid4().hex[:12]}"  # generated here, never from input
    admin = psycopg2.connect(TEST_DATABASE_URL)
    admin.autocommit = True
    admin.cursor().execute(f"CREATE SCHEMA {schema}")
    db = Database(TEST_DATABASE_URL, search_path=schema)
    migrate(db)
    try:
        yield db
    finally:
        db.close()
        admin.cursor().execute(f"DROP SCHEMA {schema} CASCADE")
        admin.close()


def make_advisory(cve: str, vendor: str, severity: str | None, exploited: bool, days_ago: int = 0) -> Advisory:
    published = NOW - timedelta(days=days_ago)
    return Advisory(
        item_id=build_item_id("cisa_kev", cve), source_name="cisa_kev", external_id=cve, title=f"{vendor} vuln",
        url=None, content="<p>Bad thing</p>", published_at=published, collected_at=NOW, raw_payload={"cve": cve},
        cve_id=cve, affected=[AffectedProduct(vendor=vendor, product="Product", ecosystem=None)],
        severity=severity, known_exploited=exploited, known_ransomware_use=None, remediation_due_date=None,
    )


def test_migrate_is_idempotent(database):
    assert migrate(database) == []


def test_upsert_counts_only_new_items_and_refreshes_existing(database):
    repo = ItemsRepository(database)
    assert repo.upsert_items([make_article("rss:a", "one"), make_article("rss:a", "two")]) == 2

    updated = make_article("rss:a", "one").model_copy(update={"content": "<p>Updated</p>"})
    assert repo.upsert_items([updated, make_article("rss:a", "three")]) == 1

    items, _ = repo.list_items(source_type=None, source_name=None, limit=10, cursor=None)
    assert len(items) == 3
    assert {item.summary for item in items if item.title == "one"} == {"Updated"}


def test_upsert_handles_duplicates_within_one_batch(database):
    item = make_article("rss:a", "one")
    assert ItemsRepository(database).upsert_items([item, item]) == 1


def test_list_items_filters_and_paginates_without_gaps(database):
    repo = ItemsRepository(database)
    repo.upsert_items([make_article("rss:a", f"article {i}") for i in range(5)]
                      + [make_advisory("CVE-2026-0001", "Acme", "high", True)])

    seen, cursor = [], None
    while True:
        page, cursor = repo.list_items(source_type="web", source_name=None, limit=2, cursor=cursor)
        seen.extend(item.title for item in page)
        if cursor is None:
            break
    assert sorted(seen) == [f"article {i}" for i in range(5)]

    advisories, _ = repo.list_items(source_type=None, source_name="cisa_kev", limit=10, cursor=None)
    assert [a.cve_id for a in advisories] == ["CVE-2026-0001"]
    assert advisories[0].affected[0].vendor == "Acme"


def test_stats(database):
    repo = ItemsRepository(database)
    repo.upsert_items([
        make_article("rss:a", "one"),
        make_advisory("CVE-2026-0001", "Acme", "critical", True),
        make_advisory("CVE-2026-0002", "Acme", None, True),
        make_advisory("CVE-2026-0003", "Globex", "low", False),
        make_advisory("CVE-2020-0004", "Initech", "high", True, days_ago=60),  # outside the window
    ])

    stats = repo.get_stats(days=14)

    assert stats.total_items == 5
    assert stats.by_source_type == {"web": 1, "social": 0, "advisory": 4}
    assert len(stats.daily_counts) == 14
    assert stats.daily_counts[-1].advisory == 3
    assert (stats.advisory_severity.critical, stats.advisory_severity.low, stats.advisory_severity.unrated,
            stats.advisory_severity.high) == (1, 1, 1, 0)
    assert stats.known_exploited == 2
    assert [(v.name, v.count) for v in stats.top_vendors] == [("Acme", 2), ("Globex", 1)]


def test_run_lifecycle_and_single_active_run(database):
    repo = RunsRepository(database)
    run_id = str(uuid.uuid4())
    repo.create_run(run_id, NOW)

    with pytest.raises(RunAlreadyActiveError):
        repo.create_run(str(uuid.uuid4()), NOW)

    repo.mark_running(run_id, NOW)
    source = RunSourceResult(source_name="rss:a", source_type="web", status="success", items=2, skipped=0,
                             error_message=None)
    repo.finish_run(run_id, status="completed", finished_at=NOW, items_collected=2, items_new=1,
                    sources=[source], error_message=None)

    run = repo.get_run(run_id)
    assert (run.status, run.items_new, run.sources) == ("completed", 1, [source])
    assert repo.list_runs(limit=1)[0].run_id == run_id
    repo.create_run(str(uuid.uuid4()), NOW)  # allowed again once the first run is finished


def test_interrupted_runs_are_failed_on_startup(database):
    repo = RunsRepository(database)
    run_id = str(uuid.uuid4())
    repo.create_run(run_id, NOW)

    assert repo.fail_interrupted_runs(NOW) == 1
    assert repo.get_run(run_id).status == "failed"
