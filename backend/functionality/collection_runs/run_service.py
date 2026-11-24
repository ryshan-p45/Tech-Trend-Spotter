import asyncio
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Protocol

from app_logging import get_logger
from functionality.data_collection.collection_core import run_collection
from functionality.data_collection.collectors.base import BaseCollector
from functionality.storage.runs_repository import RunAlreadyActiveError
from interfaces.api_interfaces import CollectionRunResponse, RunSourceResult, RunStatus
from interfaces.collection_interfaces import CollectedItem, CollectionResult

"""
Starts collection runs and records their outcome.

Data flow for one run:
    POST /v1/collection-runs
        -> request_run()  : checks no run is active and the cool-down has passed,
                            records a 'queued' run, returns it immediately (202)
        -> execute_run()  : runs in the background after the response is sent:
                            'running' -> run every collector -> save items -> 'completed'
                            (or 'failed' if something outside the collectors broke)

A run where some sources fail still 'completes': per-source failures are
recorded in `sources`. 'failed' means the run as a whole could not finish.
"""


logger = get_logger("collection_runs")


class RunCooldownError(Exception):
    """A run was requested too soon after the previous one."""

    def __init__(self, retry_after_seconds: int):
        super().__init__(f"Try again in {retry_after_seconds} seconds")
        self.retry_after_seconds = retry_after_seconds


class RunsStore(Protocol):
    """What the service needs from run storage (RunsRepository in production, a fake in tests)."""

    def create_run(self, run_id: str, requested_at: datetime) -> CollectionRunResponse: ...
    def mark_running(self, run_id: str, started_at: datetime) -> None: ...
    def finish_run(self, run_id: str, *, status: RunStatus, finished_at: datetime, items_collected: int,
                   items_new: int, sources: list[RunSourceResult], error_message: str | None) -> None: ...
    def list_runs(self, limit: int) -> list[CollectionRunResponse]: ...


class ItemsStore(Protocol):
    """What the service needs from item storage."""

    def upsert_items(self, items: list[CollectedItem]) -> int: ...


class CollectionRunService:
    """Coordinates a run: guards -> collectors -> storage."""

    def __init__(self, runs: RunsStore, items: ItemsStore,
                 build_collectors: Callable[[], list[BaseCollector]], cooldown_seconds: int):
        self._runs = runs
        self._items = items
        self._build_collectors = build_collectors  # called per run, so sources.yaml edits apply without a restart
        self._cooldown_seconds = cooldown_seconds

    def request_run(self) -> CollectionRunResponse:
        """
        Records a new queued run and returns it.
        Raises RunAlreadyActiveError (one is in progress) or RunCooldownError (too soon after the last one).
        """
        now = datetime.now(timezone.utc)
        latest = next(iter(self._runs.list_runs(limit=1)), None)
        if latest is not None and latest.status in ("queued", "running"):
            raise RunAlreadyActiveError("A collection run is already in progress")
        if latest is not None:
            self._check_cooldown(latest.requested_at, now)
        # The database also rejects a second active run, covering two requests arriving at once
        return self._runs.create_run(str(uuid.uuid4()), now)

    async def execute_run(self, run_id: str) -> None:
        """Runs every collector and saves the items. Never raises: failures are recorded on the run."""
        try:
            await asyncio.to_thread(self._runs.mark_running, run_id, datetime.now(timezone.utc))
            collectors = self._build_collectors()
            results = await run_collection(collectors, correlation_id=run_id)
            items = [item for result in results for item in result.items]
            items_new = await asyncio.to_thread(self._items.upsert_items, items)
        except Exception as error:  # anything outside the collectors (bad sources.yaml, database down...)
            logger.exception("Collection run failed", extra={"correlation_id": run_id})
            await self._record_failure(run_id, error)
            return

        await asyncio.to_thread(
            self._runs.finish_run, run_id, status="completed", finished_at=datetime.now(timezone.utc),
            items_collected=len(items), items_new=items_new,
            sources=[_source_result(result) for result in results], error_message=None,
        )
        logger.info("Collection run completed", extra={
            "correlation_id": run_id, "context": {"items_collected": len(items), "items_new": items_new},
        })

    def _check_cooldown(self, last_requested_at: datetime, now: datetime) -> None:
        """Raises RunCooldownError if the last run was requested less than cooldown_seconds ago."""
        elapsed = (now - last_requested_at).total_seconds()
        if elapsed < self._cooldown_seconds:
            raise RunCooldownError(retry_after_seconds=int(self._cooldown_seconds - elapsed) + 1)

    async def _record_failure(self, run_id: str, error: Exception) -> None:
        """Best effort: if even this write fails (e.g. database down), the startup clean-up marks it failed later."""
        try:
            await asyncio.to_thread(
                self._runs.finish_run, run_id, status="failed", finished_at=datetime.now(timezone.utc),
                items_collected=0, items_new=0, sources=[],
                # Generic on purpose: internal details stay in the logs (search by the run ID)
                error_message=f"The run stopped because of an internal {type(error).__name__}. "
                              "Check the server logs for this run ID, then start a new run.",
            )
        except Exception:
            logger.exception("Could not record failed run", extra={"correlation_id": run_id})


def _source_result(result: CollectionResult) -> RunSourceResult:
    """Per-source summary stored on the run."""
    return RunSourceResult(
        source_name=result.source_name, source_type=result.source_type, status=result.status,
        items=len(result.items), skipped=result.skipped_count,
        error_message=result.error.message if result.error else None,
    )
