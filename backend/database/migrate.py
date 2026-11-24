import sys
from pathlib import Path

from config import DATABASE_URL
from database.connection import Database, DatabaseUnavailableError

"""
Applies database migrations. Run as a separate step, never from the API:

    python -m database.migrate        (from backend/)

How it works:
    - Migrations are the numbered .sql files in database/migrations/, applied in name order.
    - Applied versions are recorded in the schema_migrations table, so each file runs once.
    - Each file runs in its own transaction: it is applied fully or not at all.
    - Never edit a migration that has been applied anywhere; add a new numbered file instead.
"""


MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def pending_migrations(applied_versions: set[str]) -> list[Path]:
    """The .sql files that haven't been applied yet, in the order they must run."""
    return [path for path in sorted(MIGRATIONS_DIR.glob("*.sql")) if path.stem not in applied_versions]


def migrate(database: Database) -> list[str]:
    """Applies every pending migration. Returns the versions applied in this call."""
    with database.connection() as conn, conn.cursor() as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version    TEXT        PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        cursor.execute("SELECT version FROM schema_migrations LIMIT 10000")
        applied = {row[0] for row in cursor.fetchall()}

    newly_applied: list[str] = []
    for path in pending_migrations(applied):
        # One transaction per file: the SQL and its schema_migrations row commit together
        with database.connection() as conn, conn.cursor() as cursor:
            cursor.execute(path.read_text(encoding="utf-8"))
            cursor.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (path.stem,))
        newly_applied.append(path.stem)
    return newly_applied


if __name__ == "__main__":
    db = Database(DATABASE_URL)
    try:
        applied_now = migrate(db)
    except DatabaseUnavailableError as error:
        print(f"Could not reach the database: {error}\nCheck DATABASE_URL in backend/.env and that Postgres is running.")
        sys.exit(1)
    finally:
        db.close()
    print("Applied: " + ", ".join(applied_now) if applied_now else "Database is up to date.")
