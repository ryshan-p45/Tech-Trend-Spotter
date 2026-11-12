import hashlib
from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field, HttpUrl, field_validator

"""
Standard data contract between data_collection and data_processing.

Every collector MUST output one of the item models below. data_processing
only depends on these models - never on a specific collector - so collectors
can be added, changed or removed without touching processing code.

Web and social data are kept as separate models (and separate result
batches) so they can be handled differently downstream:
    - WebArticle  -> blogs, news sites, advisories, RSS feeds
    - SocialPost  -> community platforms (Hacker News, Reddit, Mastodon...)
"""


# Source categories. Adding a new category is a deliberate contract change.
SourceType = Literal["web", "social"]

# Outcome of a single collector run
CollectionStatus = Literal["success", "failed"]

# Whether a failure is worth retrying later (e.g. timeout) or needs a developer (e.g. bad parsing)
ErrorCategory = Literal["retryable", "non_retryable"]

# Maximum length of CollectedItem.content; collectors truncate longer text to this
MAX_CONTENT_LENGTH = 20_000


def build_item_id(source_name: str, external_id: str) -> str:
    """
    Deterministic ID for an item: the same post collected twice gets the same ID.
    This lets storage/processing de-duplicate across collection runs.
    """
    return hashlib.sha256(f"{source_name}:{external_id}".encode("utf-8")).hexdigest()


class CollectedItem(BaseModel):
    """Fields every collected item has, regardless of where it came from."""

    item_id: str = Field(description="Deterministic SHA-256 of source_name + external_id, used for de-duplication")
    source_type: SourceType = Field(description="Category of the source: 'web' or 'social'")
    source_name: str = Field(min_length=1, max_length=100, description="Identifier of the specific source, e.g. 'hacker_news' or 'rss:krebsonsecurity'")
    external_id: str = Field(min_length=1, max_length=500, description="The item's ID at the source (post ID, feed entry GUID, or URL)")
    title: str = Field(min_length=1, max_length=500, description="Headline / post title")
    url: HttpUrl | None = Field(description="Link to the original content. Null when the source provides none")
    content: str | None = Field(max_length=MAX_CONTENT_LENGTH, description="Summary or body text as provided by the source. Null when unavailable")
    tags: list[str] = Field(default_factory=list, description="Source-provided categories/tags. Empty when none")
    published_at: datetime | None = Field(description="When the source published the item (UTC). Null if unknown")
    collected_at: datetime = Field(description="When we collected the item (UTC)")
    raw_payload: dict[str, Any] = Field(description="Original source record, kept so processing can extract more fields later without re-collecting")

    @field_validator("published_at", "collected_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        """Reject naive datetimes so every timestamp is unambiguously UTC."""
        if value is not None and value.tzinfo is None:
            raise ValueError("datetime must be timezone-aware (UTC)")
        return value


class WebArticle(CollectedItem):
    """Content from websites, blogs, news and RSS feeds."""

    source_type: Literal["web"] = "web"
    site_name: str | None = Field(max_length=200, description="Human-readable publisher name, e.g. 'Krebs on Security'. Null if unknown")


class SocialPost(CollectedItem):
    """Content from community / social platforms, including engagement signals."""

    source_type: Literal["social"] = "social"
    score: int | None = Field(description="Platform score (upvotes/points/favourites). Null if the platform has none")
    comment_count: int | None = Field(description="Number of comments/replies. Null if unavailable")
    discussion_url: HttpUrl | None = Field(description="Link to the discussion thread on the platform. Null if unavailable")


class CollectionError(BaseModel):
    """Structured description of why a collector run failed."""

    category: ErrorCategory = Field(description="'retryable' (try again later) or 'non_retryable' (needs a developer)")
    message: str = Field(description="Human-readable explanation of what went wrong")


class CollectionResult(BaseModel):
    """
    Output of one collector run. Always the same shape:
    on success `error` is null; on failure `items` is empty and `error` is set.
    """

    correlation_id: str = Field(description="ID shared by all collectors in the same run, for tracing")
    source_name: str = Field(description="Which collector produced this result")
    source_type: SourceType = Field(description="Category of items in this batch - batches never mix web and social")
    status: CollectionStatus = Field(description="'success' or 'failed'")
    items: list[WebArticle] | list[SocialPost] = Field(description="Collected items. Empty on failure")
    skipped_count: int = Field(ge=0, description="Records dropped because they failed validation")
    error: CollectionError | None = Field(description="Failure details. Null on success")
    started_at: datetime = Field(description="Run start time (UTC)")
    finished_at: datetime = Field(description="Run end time (UTC)")
