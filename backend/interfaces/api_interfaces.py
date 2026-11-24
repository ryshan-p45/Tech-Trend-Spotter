from datetime import date, datetime
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field

from interfaces.collection_interfaces import AffectedProduct, Severity, SourceType

"""
Public API contract (/v1). Every response uses one of three envelopes:

    Single resource : {"data": {...}}
    List            : {"data": [...], "pagination": {"next_cursor": "...", "limit": 50}}
    Error           : {"error": {"code": "...", "message": "..."}}

Rules:
    - Dates are ISO 8601 in UTC.
    - A field that doesn't apply to an item is null (e.g. `score` on an advisory),
      so every item has exactly the same shape regardless of its source type.
"""


T = TypeVar("T")

# Lifecycle of a collection run
RunStatus = Literal["queued", "running", "completed", "failed"]


# ---------- Envelopes ----------

class DataResponse(BaseModel, Generic[T]):
    """Envelope for a single resource."""

    data: T


class Pagination(BaseModel):
    """Cursor pagination details. Pass `next_cursor` back as `cursor` to get the next page."""

    next_cursor: str | None = Field(description="Opaque cursor for the next page. Null on the last page")
    limit: int = Field(description="Maximum number of records per page used for this request")


class PageResponse(BaseModel, Generic[T]):
    """Envelope for a list of resources."""

    data: list[T]
    pagination: Pagination


class ErrorDetail(BaseModel):
    code: str = Field(description="Stable machine-readable error code, e.g. 'invalid_request'")
    message: str = Field(description="What went wrong and what to do next, in plain language")


class ErrorResponse(BaseModel):
    """Envelope for every error response."""

    error: ErrorDetail


# ---------- Items ----------

class ItemResponse(BaseModel):
    """One collected item. Type-specific fields are null when they don't apply to the item's source type."""

    item_id: str = Field(description="Stable ID; the same item always has the same ID")
    source_type: SourceType
    source_name: str = Field(description="e.g. 'hacker_news', 'cisa_kev', 'rss:krebsonsecurity'")
    title: str
    url: str | None = Field(description="Link to the original content. Null if the source has none")
    summary: str | None = Field(description="Plain-text excerpt of the content (no HTML), at most 300 characters")
    tags: list[str]
    published_at: datetime | None = Field(description="When the source published it. Null if unknown")
    first_collected_at: datetime = Field(description="When we first collected it")
    # web
    site_name: str | None = Field(description="Publisher name (web items only)")
    # social
    score: int | None = Field(description="Points/upvotes (social items only)")
    comment_count: int | None = Field(description="Number of comments (social items only)")
    discussion_url: str | None = Field(description="Link to the discussion thread (social items only)")
    # advisory
    cve_id: str | None = Field(description="CVE identifier (advisories only)")
    affected: list[AffectedProduct] | None = Field(description="Affected products/packages (advisories only)")
    severity: Severity | None = Field(description="Normalised severity (advisories only; null if unrated)")
    known_exploited: bool | None = Field(description="Confirmed exploited in the wild (advisories only)")
    known_ransomware_use: bool | None = Field(description="Used in ransomware campaigns (advisories only; null if unknown)")
    remediation_due_date: date | None = Field(description="Deadline set by the source for applying a fix (advisories only)")


# ---------- Item stats ----------

class SourceCount(BaseModel):
    source_name: str
    source_type: SourceType
    count: int


class DailyCount(BaseModel):
    """Items per day, by date of publication (or first collection when the source gives no date)."""

    date: date
    web: int
    social: int
    advisory: int


class NamedCount(BaseModel):
    name: str
    count: int


class SeverityCounts(BaseModel):
    critical: int
    high: int
    medium: int
    low: int
    unrated: int


class ItemStatsResponse(BaseModel):
    """Summary of everything collected, for the dashboard. Advisory figures cover the last `days` days."""

    days: int = Field(description="Size of the window, in days, used for daily_counts and the advisory figures")
    total_items: int = Field(description="All items ever collected")
    by_source_type: dict[SourceType, int] = Field(description="All items ever collected, per source type")
    by_source: list[SourceCount] = Field(description="All items ever collected, per source, largest first")
    daily_counts: list[DailyCount] = Field(description="One entry per day in the window, oldest first; days with no items are 0")
    advisory_severity: SeverityCounts = Field(description="Advisories in the window, per severity")
    known_exploited: int = Field(description="Advisories in the window confirmed as exploited in the wild")
    top_vendors: list[NamedCount] = Field(description="Most-affected vendors in the window (up to 8)")
    top_ecosystems: list[NamedCount] = Field(description="Most-affected package ecosystems in the window (up to 8)")


# ---------- Collection runs ----------

class RunSourceResult(BaseModel):
    """Outcome of one collector within a run."""

    source_name: str
    source_type: SourceType
    status: Literal["success", "failed"]
    items: int = Field(description="Items collected from this source")
    skipped: int = Field(description="Records dropped because they didn't fit the schema")
    error_message: str | None = Field(description="Why the source failed. Null on success")


class CollectionRunResponse(BaseModel):
    """A collection run. Poll GET /v1/collection-runs/{run_id} until status is 'completed' or 'failed'."""

    run_id: str
    status: RunStatus
    requested_at: datetime
    started_at: datetime | None = Field(description="Null while queued")
    finished_at: datetime | None = Field(description="Null until completed or failed")
    items_collected: int = Field(description="Items returned by all sources in this run")
    items_new: int = Field(description="Items seen for the first time in this run")
    sources: list[RunSourceResult] = Field(description="Per-source outcome. Empty until the run finishes")
    error_message: str | None = Field(description="Why the whole run failed. Null otherwise")
