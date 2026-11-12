from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

"""
Schema for the data collection sources file (sources.yaml).

The YAML file is validated against these models when it is loaded, so a
typo, unknown field or non-https URL fails loudly at startup instead of
causing confusing errors during a collection run.
"""


def _require_https(url: HttpUrl) -> HttpUrl:
    """Shared rule: every source must be fetched over https."""
    if url.scheme != "https":
        raise ValueError("URL must use https")
    return url


class StrictConfigModel(BaseModel):
    """Base for config models: unknown keys are rejected so typos (e.g. 'max_item') are caught."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class RssFeedConfig(StrictConfigModel):
    """One RSS/Atom feed to collect."""

    key: str = Field(pattern=r"^[a-z0-9_]{1,50}$", description="Short stable slug; the source_name becomes 'rss:<key>'")
    url: HttpUrl = Field(description="Feed URL (https only)")
    site_name: str = Field(min_length=1, max_length=200, description="Human-readable publisher name")
    enabled: bool = Field(default=True, description="Set to false to stop collecting without deleting the entry")

    _check_url = field_validator("url")(_require_https)


class HackerNewsConfig(StrictConfigModel):
    """Settings for the Hacker News collector (Algolia search API)."""

    enabled: bool = Field(default=True, description="Set to false to disable this collector")
    search_url: HttpUrl = Field(description="Algolia HN search endpoint (https only)")
    item_url_template: str = Field(description="Discussion link template; must contain '{item_id}'")
    min_points: int = Field(default=50, ge=0, description="Only collect stories with at least this many points")
    max_items: int = Field(default=50, ge=1, le=100, description="Maximum stories per run (1-100)")

    _check_url = field_validator("search_url")(_require_https)

    @field_validator("item_url_template")
    @classmethod
    def require_item_id_placeholder(cls, value: str) -> str:
        if not value.startswith("https://") or "{item_id}" not in value:
            raise ValueError("item_url_template must be an https URL containing '{item_id}'")
        return value


class WebSourcesConfig(StrictConfigModel):
    """All web sources (blogs, news, feeds)."""

    rss_feeds: list[RssFeedConfig] = Field(default_factory=list, description="RSS/Atom feeds to collect")

    @field_validator("rss_feeds")
    @classmethod
    def require_unique_keys(cls, feeds: list[RssFeedConfig]) -> list[RssFeedConfig]:
        """Duplicate keys would produce colliding source_names and item IDs."""
        keys = [feed.key for feed in feeds]
        duplicates = sorted({key for key in keys if keys.count(key) > 1})
        if duplicates:
            raise ValueError(f"duplicate rss feed keys: {', '.join(duplicates)}")
        return feeds


class SocialSourcesConfig(StrictConfigModel):
    """All social/community sources. Each platform is optional - omit it to disable."""

    hacker_news: HackerNewsConfig | None = Field(default=None, description="Hacker News settings")


class SourcesConfig(StrictConfigModel):
    """Root of sources.yaml. Web and social sources are kept in separate sections."""

    web: WebSourcesConfig = Field(default_factory=WebSourcesConfig)
    social: SocialSourcesConfig = Field(default_factory=SocialSourcesConfig)
