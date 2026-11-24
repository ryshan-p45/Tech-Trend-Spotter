from datetime import datetime

from psycopg2 import errors as pg_errors
from psycopg2.extras import Json

from database.connection import Database
from interfaces.api_interfaces import CollectionRunResponse, RunSourceResult, RunStatus

"""
Reads and writes collection runs in Postgres (table: collection_runs).

A run moves through: queued -> running -> completed | failed.
The database allows only one queued/running run at a time (unique partial
index), so create_run() is safe even when two requests arrive together.
"""


# Columns read for a run, in the order _row_to_run expects
RUN_COLUMNS = "run_id, status, requested_at, started_at, finished_at, items_collected, items_new, sources, error_message"


class RunAlreadyActiveError(Exception):
    """A run is already queued or running. The caller should wait for it to finish."""


class RunsRepository:
    """All SQL for the collection_runs table."""

    def __init__(self, database: Database):
        self._database = database

    def create_run(self, run_id: str, requested_at: datetime) -> CollectionRunResponse:
        """Records a new queued run. Raises RunAlreadyActiveError if one is already queued or running."""
        try:
            with self._database.connection() as conn, conn.cursor() as cursor:
                cursor.execute(f"""
                    INSERT INTO collection_runs (run_id, status, requested_at) VALUES (%s, 'queued', %s)
                    RETURNING {RUN_COLUMNS}
                """, (run_id, requested_at))
                return _row_to_run(cursor.fetchone())
        except pg_errors.UniqueViolation as error:
            raise RunAlreadyActiveError("A collection run is already in progress") from error

    def mark_running(self, run_id: str, started_at: datetime) -> None:
        with self._database.connection() as conn, conn.cursor() as cursor:
            cursor.execute("UPDATE collection_runs SET status = 'running', started_at = %s WHERE run_id = %s",
                           (started_at, run_id))

    def finish_run(self, run_id: str, *, status: RunStatus, finished_at: datetime, items_collected: int,
                   items_new: int, sources: list[RunSourceResult], error_message: str | None) -> None:
        """Stores the final outcome of a run ('completed' or 'failed')."""
        with self._database.connection() as conn, conn.cursor() as cursor:
            cursor.execute("""
                UPDATE collection_runs
                SET status = %s, finished_at = %s, items_collected = %s, items_new = %s, sources = %s, error_message = %s
                WHERE run_id = %s
            """, (status, finished_at, items_collected, items_new,
                  Json([source.model_dump(mode="json") for source in sources]), error_message, run_id))

    def get_run(self, run_id: str) -> CollectionRunResponse | None:
        with self._database.connection() as conn, conn.cursor() as cursor:
            cursor.execute(f"SELECT {RUN_COLUMNS} FROM collection_runs WHERE run_id = %s LIMIT 1", (run_id,))
            row = cursor.fetchone()
        return _row_to_run(row) if row else None

    def list_runs(self, limit: int) -> list[CollectionRunResponse]:
        """Most recently requested runs first."""
        with self._database.connection() as conn, conn.cursor() as cursor:
            cursor.execute(f"SELECT {RUN_COLUMNS} FROM collection_runs ORDER BY requested_at DESC LIMIT %s", (limit,))
            return [_row_to_run(row) for row in cursor.fetchall()]

    def fail_interrupted_runs(self, finished_at: datetime) -> int:
        """
        Marks queued/running runs as failed. Called on API startup: a run still 'active' at that
        point was interrupted by a restart and would otherwise block new runs forever.
        """
        with self._database.connection() as conn, conn.cursor() as cursor:
            cursor.execute("""
                UPDATE collection_runs
                SET status = 'failed', finished_at = %s,
                    error_message = 'The server restarted before this run finished. Start a new run.'
                WHERE status IN ('queued', 'running')
            """, (finished_at,))
            return cursor.rowcount


def _row_to_run(row: tuple) -> CollectionRunResponse:
    run_id, status, requested_at, started_at, finished_at, items_collected, items_new, sources, error_message = row
    return CollectionRunResponse(
        run_id=str(run_id), status=status, requested_at=requested_at, started_at=started_at,
        finished_at=finished_at, items_collected=items_collected, items_new=items_new,
        sources=[RunSourceResult(**source) for source in sources or []], error_message=error_message,
    )
