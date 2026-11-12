import asyncio
import json
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from app_logging import get_logger
from functionality.data_collection.http_client import FetchError, SourceHttpClient
from interfaces.collection_interfaces import (
    MAX_CONTENT_LENGTH, CollectedItem, CollectionError, CollectionResult, SourceType,
)

"""
Base class every collector extends.

A collector has exactly two jobs, implemented by subclasses:
    1. fetch_records()  - get raw records from ONE source (side effect: network)
    2. parse_record()   - turn ONE raw record into a standard item model (pure logic)

BaseCollector.collect() wraps those two steps with the shared rules:
    - The whole run has a time limit, so a slow source can never hang a run
    - Any failure is caught and returned as a structured CollectionResult,
      so one broken source never breaks the other collectors
    - Records that don't fit the schema are skipped and counted, not fatal
"""


logger = get_logger("data_collection.collector")


class SourceFormatError(Exception):
    """The source responded, but the data was not in the shape we expected (needs a developer to look at)."""


def to_json_safe(record: Any) -> dict[str, Any]:
    """Converts a raw record into plain JSON types so it can be stored (e.g. in a Postgres JSONB column)."""
    return json.loads(json.dumps(record, default=str))


def truncate_content(text: str | None) -> str | None:
    """Keeps long bodies within the schema limit instead of rejecting the whole item. Empty text becomes None."""
    if not text:
        return None
    return text[:MAX_CONTENT_LENGTH]


class BaseCollector(ABC):
    """Template for all collectors. Subclasses set the class attributes and implement the two abstract methods."""

    # Unique identifier for the source, e.g. "hacker_news" or "rss:krebsonsecurity"
    source_name: str
    # "web" or "social" - decides which item model the collector must output
    source_type: SourceType
    # Maximum seconds a full run (including retries) may take
    run_timeout_seconds: float = 120.0

    @abstractmethod
    async def fetch_records(self, http: SourceHttpClient, correlation_id: str) -> list[dict[str, Any]]:
        """Fetch raw records from the source. Raise FetchError or SourceFormatError on failure."""

    @abstractmethod
    def parse_record(self, record: dict[str, Any], collected_at: datetime) -> CollectedItem:
        """Convert one raw record to a WebArticle or SocialPost. Raise ValueError/ValidationError if it doesn't fit."""

    async def collect(self, http: SourceHttpClient, correlation_id: str) -> CollectionResult:
        """Runs the collector end to end. Never raises - failures come back as a 'failed' CollectionResult."""
        started_at = datetime.now(timezone.utc)
        logger.info("Collector started", extra={
            "correlation_id": correlation_id, "context": {"source_name": self.source_name},
        })

        try:
            records = await asyncio.wait_for(self.fetch_records(http, correlation_id), timeout=self.run_timeout_seconds)
        except TimeoutError:
            return self._failed(correlation_id, started_at, "retryable",
                                f"Collector exceeded its {self.run_timeout_seconds}s time limit")
        except FetchError as error:
            return self._failed(correlation_id, started_at, "retryable" if error.retryable else "non_retryable", str(error))
        except SourceFormatError as error:
            return self._failed(correlation_id, started_at, "non_retryable", f"Unexpected data format: {error}")
        except Exception as error:  # last-resort guard so one buggy collector can't crash the whole run
            logger.exception("Unexpected collector error", extra={
                "correlation_id": correlation_id, "context": {"source_name": self.source_name},
            })
            return self._failed(correlation_id, started_at, "non_retryable", f"Unexpected error: {error}")

        items, skipped_count = self._parse_all(records, correlation_id)
        finished_at = datetime.now(timezone.utc)
        logger.info("Collector finished", extra={
            "correlation_id": correlation_id,
            "context": {"source_name": self.source_name, "items": len(items), "skipped": skipped_count},
        })
        return CollectionResult(
            correlation_id=correlation_id, source_name=self.source_name, source_type=self.source_type,
            status="success", items=items, skipped_count=skipped_count, error=None,
            started_at=started_at, finished_at=finished_at,
        )

    def _parse_all(self, records: list[dict[str, Any]], correlation_id: str) -> tuple[list[CollectedItem], int]:
        """Parses every record; invalid ones are logged and counted instead of failing the whole batch."""
        collected_at = datetime.now(timezone.utc)
        items: list[CollectedItem] = []
        skipped_count = 0

        for record in records:
            try:
                items.append(self.parse_record(record, collected_at))
            except (ValueError, ValidationError, KeyError, TypeError) as error:
                skipped_count += 1
                logger.warning("Skipped invalid record", extra={
                    "correlation_id": correlation_id,
                    "context": {"source_name": self.source_name, "error": str(error)[:500]},
                })

        return items, skipped_count

    def _failed(self, correlation_id: str, started_at: datetime, category: str, message: str) -> CollectionResult:
        """Builds the standard failure result and logs it."""
        logger.error("Collector failed", extra={
            "correlation_id": correlation_id,
            "context": {"source_name": self.source_name, "category": category, "error": message},
        })
        return CollectionResult(
            correlation_id=correlation_id, source_name=self.source_name, source_type=self.source_type,
            status="failed", items=[], skipped_count=0,
            error=CollectionError(category=category, message=message),
            started_at=started_at, finished_at=datetime.now(timezone.utc),
        )
