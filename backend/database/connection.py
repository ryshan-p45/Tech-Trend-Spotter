import threading
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg2
from psycopg2.extensions import connection as PgConnection
from psycopg2.pool import ThreadedConnectionPool

from app_logging import get_logger

"""
Postgres connection handling for the whole backend.

- One shared connection pool per process, created lazily on first use, so the
  API still starts (and /v1/health still answers) when the database is down.
- Every connection has a statement timeout, so no query can block forever.
- `Database.connection()` is the only way code gets a connection. It commits on
  success, rolls back on any error, and always returns the connection to the pool.
- If Postgres can't be reached, DatabaseUnavailableError is raised. The API turns
  that into a 503 with a readable message instead of a crash.
"""


logger = get_logger("database")


class DatabaseUnavailableError(Exception):
    """Postgres could not be reached. Retryable: the database may come back."""


class Database:
    """Lazily created, thread-safe connection pool."""

    def __init__(self, dsn: str, *, min_connections: int = 1, max_connections: int = 10,
                 connect_timeout_seconds: int = 5, statement_timeout_ms: int = 10_000,
                 search_path: str | None = None):
        self._dsn = dsn
        self._min_connections = min_connections
        self._max_connections = max_connections
        self._connect_timeout_seconds = connect_timeout_seconds
        self._statement_timeout_ms = statement_timeout_ms
        # Optional schema to use instead of 'public' (tests use a throwaway schema)
        self._search_path = search_path
        self._pool: ThreadedConnectionPool | None = None
        self._pool_lock = threading.Lock()

    @contextmanager
    def connection(self) -> Iterator[PgConnection]:
        """
        Yields a pooled connection wrapped in a transaction.
        Commit on success, rollback on error. Broken connections are discarded, not reused.
        """
        pool = self._get_pool()
        try:
            conn = pool.getconn()
        except psycopg2.Error as error:
            raise DatabaseUnavailableError(f"Could not get a database connection: {error}") from error

        broken = False
        try:
            yield conn
            conn.commit()
        except psycopg2.OperationalError as error:
            # Lost connection / server gone: the connection can't be reused
            broken = True
            _safe_rollback(conn)
            raise DatabaseUnavailableError(f"Database connection failed: {error}") from error
        except Exception:
            _safe_rollback(conn)
            raise
        finally:
            pool.putconn(conn, close=broken or conn.closed != 0)

    def close(self) -> None:
        """Closes every pooled connection (called on API shutdown)."""
        with self._pool_lock:
            if self._pool is not None:
                self._pool.closeall()
                self._pool = None

    def _get_pool(self) -> ThreadedConnectionPool:
        """Creates the pool on first use. Raises DatabaseUnavailableError if Postgres can't be reached."""
        if not self._dsn:
            raise DatabaseUnavailableError("DATABASE_URL is not set. Add it to backend/.env.")

        with self._pool_lock:
            if self._pool is None:
                try:
                    options = f"-c statement_timeout={self._statement_timeout_ms}"
                    if self._search_path:
                        options += f" -c search_path={self._search_path}"
                    self._pool = ThreadedConnectionPool(
                        self._min_connections, self._max_connections, self._dsn,
                        connect_timeout=self._connect_timeout_seconds, options=options,
                    )
                except psycopg2.OperationalError as error:
                    # Logged without the DSN: it contains the password
                    logger.error("Could not connect to the database", extra={"context": {"error": str(error)}})
                    raise DatabaseUnavailableError(f"Could not connect to the database: {error}") from error
            return self._pool


def _safe_rollback(conn: PgConnection) -> None:
    """Rolls back if the connection is still usable; ignores errors from an already-dead connection."""
    try:
        if conn.closed == 0:
            conn.rollback()
    except psycopg2.Error:
        pass
