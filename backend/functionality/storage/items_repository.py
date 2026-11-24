import base64
import html
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from psycopg2.extras import Json, execute_values

from database.connection import Database
from interfaces.api_interfaces import (
    DailyCount, ItemResponse, ItemStatsResponse, NamedCount, SeverityCounts, SourceCount,
)
from interfaces.collection_interfaces import CollectedItem, SourceType

"""
Reads and writes collected items in Postgres (table: collected_items).

Writes:  upsert_items()  - insert new items, refresh existing ones (de-duplicated by item_id)
Reads:   list_items()    - newest first, filtered, cursor-paginated
         get_stats()     - counts for the dashboard

Every query is parameterised and has a LIMIT. Common fields are columns; the
fields specific to one item type (score, severity, affected...) live in the
`details` JSONB column so new item types don't need a migration.
"""


# Fields stored as their own columns; everything else on an item model goes into `details`
COMMON_FIELDS = set(CollectedItem.model_fields)

# Length of the plain-text summary returned by the API
SUMMARY_LENGTH = 300

# Number of entries in the top vendors / ecosystems lists
TOP_LIST_SIZE = 8

# Columns read for an item (never SELECT *; raw_payload and full content are not sent to the API)
ITEM_COLUMNS = "item_id, source_type, source_name, title, url, content, tags, published_at, first_collected_at, details, sort_at"


class InvalidCursorError(ValueError):
    """The pagination cursor sent by the client is malformed or was tampered with."""


class ItemsRepository:
    """All SQL for the collected_items table."""

    def __init__(self, database: Database):
        self._database = database

    # ---------- Writes ----------

    def upsert_items(self, items: list[CollectedItem]) -> int:
        """
        Saves items in one transaction. New items are inserted; items seen before get their
        content and last_collected_at refreshed (first_collected_at is kept).
        Returns how many items were new.
        """
        unique_items = list({item.item_id: item for item in items}.values())  # a batch may repeat an item
        if not unique_items:
            return 0

        rows = [_item_to_row(item) for item in unique_items]
        with self._database.connection() as conn, conn.cursor() as cursor:
            inserted_flags = execute_values(cursor, """
                INSERT INTO collected_items (item_id, source_type, source_name, external_id, title, url, content,
                                             tags, published_at, details, raw_payload, first_collected_at, last_collected_at)
                VALUES %s
                ON CONFLICT (item_id) DO UPDATE SET
                    title = EXCLUDED.title, url = EXCLUDED.url, content = EXCLUDED.content, tags = EXCLUDED.tags,
                    published_at = EXCLUDED.published_at, details = EXCLUDED.details,
                    raw_payload = EXCLUDED.raw_payload, last_collected_at = EXCLUDED.last_collected_at
                RETURNING (xmax = 0)
            """, rows, page_size=500, fetch=True)  # xmax = 0 only for freshly inserted rows
        return sum(1 for (was_inserted,) in inserted_flags if was_inserted)

    # ---------- Reads ----------

    def list_items(self, *, source_type: SourceType | None, source_name: str | None,
                   limit: int, cursor: str | None) -> tuple[list[ItemResponse], str | None]:
        """Newest items first. Returns (items, next_cursor); next_cursor is None on the last page."""
        conditions: list[str] = []
        params: list[Any] = []
        if source_type is not None:
            conditions.append("source_type = %s")
            params.append(source_type)
        if source_name is not None:
            conditions.append("source_name = %s")
            params.append(source_name)
        if cursor is not None:
            # Keyset pagination: everything strictly after the last item of the previous page
            cursor_sort_at, cursor_item_id = decode_cursor(cursor)
            conditions.append("(sort_at, item_id) < (%s, %s)")
            params.extend([cursor_sort_at, cursor_item_id])

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit + 1)  # one extra row tells us whether another page exists
        with self._database.connection() as conn, conn.cursor() as db_cursor:
            db_cursor.execute(f"""
                SELECT {ITEM_COLUMNS} FROM collected_items
                {where}
                ORDER BY sort_at DESC, item_id DESC
                LIMIT %s
            """, params)
            rows = db_cursor.fetchall()

        page_rows = rows[:limit]
        next_cursor = encode_cursor(page_rows[-1][10], page_rows[-1][0]) if len(rows) > limit else None
        return [_row_to_item(row) for row in page_rows], next_cursor

    def get_stats(self, days: int) -> ItemStatsResponse:
        """Totals for everything collected, plus daily counts and advisory figures for the last `days` days."""
        today = datetime.now(timezone.utc).date()
        window_start_date = today - timedelta(days=days - 1)
        window_start = datetime.combine(window_start_date, datetime.min.time(), tzinfo=timezone.utc)

        with self._database.connection() as conn, conn.cursor() as cursor:
            per_source = _query_per_source(cursor)
            daily_rows = _query_daily(cursor, window_start)
            severity_rows = _query_advisory_severity(cursor, window_start)
            top_vendors = _query_top_affected(cursor, "vendor", window_start)
            top_ecosystems = _query_top_affected(cursor, "ecosystem", window_start)

        by_source_type = {"web": 0, "social": 0, "advisory": 0}
        for source in per_source:
            by_source_type[source.source_type] += source.count

        severity = {"critical": 0, "high": 0, "medium": 0, "low": 0, "unrated": 0}
        known_exploited = 0
        for severity_name, count, exploited_count in severity_rows:
            severity[severity_name if severity_name in severity else "unrated"] += count
            known_exploited += exploited_count

        return ItemStatsResponse(
            days=days,
            total_items=sum(by_source_type.values()),
            by_source_type=by_source_type,
            by_source=per_source,
            daily_counts=_fill_daily_counts(daily_rows, window_start_date, days),
            advisory_severity=SeverityCounts(**severity),
            known_exploited=known_exploited,
            top_vendors=top_vendors,
            top_ecosystems=top_ecosystems,
        )


# ---------- Stats queries (one function per question) ----------

def _query_per_source(cursor) -> list[SourceCount]:
    """How many items each source has produced, largest first."""
    cursor.execute("""
        SELECT source_name, source_type, COUNT(*) FROM collected_items
        GROUP BY source_name, source_type ORDER BY COUNT(*) DESC LIMIT 200
    """)
    return [SourceCount(source_name=name, source_type=kind, count=count) for name, kind, count in cursor.fetchall()]


def _query_daily(cursor, window_start: datetime) -> list[tuple]:
    """(date, source_type, count) for every day in the window that has items."""
    cursor.execute("""
        SELECT (sort_at AT TIME ZONE 'UTC')::date AS day, source_type, COUNT(*) FROM collected_items
        WHERE sort_at >= %s
        GROUP BY day, source_type LIMIT 5000
    """, (window_start,))
    return cursor.fetchall()


def _query_advisory_severity(cursor, window_start: datetime) -> list[tuple]:
    """(severity or NULL, advisory count, of which known exploited) for advisories in the window."""
    cursor.execute("""
        SELECT details->>'severity', COUNT(*), COUNT(*) FILTER (WHERE details->>'known_exploited' = 'true')
        FROM collected_items
        WHERE source_type = 'advisory' AND sort_at >= %s
        GROUP BY details->>'severity' LIMIT 10
    """, (window_start,))
    return cursor.fetchall()


def _query_top_affected(cursor, field: str, window_start: datetime) -> list[NamedCount]:
    """Most common vendors or ecosystems across advisories' `affected` lists in the window."""
    if field not in {"vendor", "ecosystem"}:  # allowlist: `field` is used as a JSON key, never user input
        raise ValueError(f"Unsupported affected field: {field}")
    cursor.execute("""
        SELECT affected->>%s AS name, COUNT(DISTINCT item_id) FROM collected_items
        CROSS JOIN LATERAL jsonb_array_elements(details->'affected') AS affected
        WHERE source_type = 'advisory' AND sort_at >= %s AND affected->>%s IS NOT NULL
        GROUP BY name ORDER BY COUNT(DISTINCT item_id) DESC, name LIMIT %s
    """, (field, window_start, field, TOP_LIST_SIZE))
    return [NamedCount(name=name, count=count) for name, count in cursor.fetchall()]


# ---------- Mapping helpers (pure, unit tested) ----------

def _fill_daily_counts(rows: list[tuple], window_start_date, days: int) -> list[DailyCount]:
    """Turns sparse (date, type, count) rows into one entry per day, with zeros for empty days."""
    counts = {window_start_date + timedelta(days=offset): {"web": 0, "social": 0, "advisory": 0} for offset in range(days)}
    for day, source_type, count in rows:
        if day in counts:
            counts[day][source_type] = count
    return [DailyCount(date=day, **per_type) for day, per_type in counts.items()]


def _item_to_row(item: CollectedItem) -> tuple:
    """Column values for one item, in the INSERT column order."""
    details = item.model_dump(mode="json", exclude=COMMON_FIELDS)
    return (
        item.item_id, item.source_type, item.source_name, item.external_id, item.title,
        str(item.url) if item.url else None, item.content, item.tags, item.published_at,
        Json(details), Json(item.raw_payload), item.collected_at, item.collected_at,
    )


def _row_to_item(row: tuple) -> ItemResponse:
    """Builds the API item from a row selected with ITEM_COLUMNS."""
    item_id, source_type, source_name, title, url, content, tags, published_at, first_collected_at, details, _ = row
    return ItemResponse(
        item_id=item_id, source_type=source_type, source_name=source_name, title=title, url=url,
        summary=to_plain_text_summary(content), tags=tags or [], published_at=published_at,
        first_collected_at=first_collected_at,
        site_name=details.get("site_name"),
        score=details.get("score"),
        comment_count=details.get("comment_count"),
        discussion_url=details.get("discussion_url"),
        cve_id=details.get("cve_id"),
        affected=details.get("affected") if source_type == "advisory" else None,
        severity=details.get("severity"),
        known_exploited=details.get("known_exploited"),
        known_ransomware_use=details.get("known_ransomware_use"),
        remediation_due_date=details.get("remediation_due_date"),
    )


def to_plain_text_summary(content: str | None, max_length: int = SUMMARY_LENGTH) -> str | None:
    """Strips HTML tags and entities, collapses whitespace, and cuts at a word boundary with an ellipsis."""
    if not content:
        return None
    text = html.unescape(re.sub(r"<[^>]+>", " ", content))
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return None
    if len(text) <= max_length:
        return text
    cut = text[:max_length - 1].rsplit(" ", 1)[0] or text[:max_length - 1]
    return cut.rstrip(" ,.;:") + "…"


def encode_cursor(sort_at: datetime, item_id: str) -> str:
    """Opaque cursor pointing at the last item of a page."""
    payload = json.dumps({"sort_at": sort_at.isoformat(), "item_id": item_id})
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")


def decode_cursor(cursor: str) -> tuple[datetime, str]:
    """Reverses encode_cursor. Raises InvalidCursorError for anything that isn't a cursor we issued."""
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode("ascii")))
        sort_at = datetime.fromisoformat(payload["sort_at"])
        item_id = payload["item_id"]
    except (ValueError, KeyError, TypeError, UnicodeError) as error:
        raise InvalidCursorError("Invalid pagination cursor") from error
    if sort_at.tzinfo is None or not isinstance(item_id, str) or not re.fullmatch(r"[0-9a-f]{64}", item_id):
        raise InvalidCursorError("Invalid pagination cursor")
    return sort_at, item_id
