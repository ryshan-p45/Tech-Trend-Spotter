from pathlib import Path

import yaml
from pydantic import ValidationError

from functionality.data_collection.collectors.base import BaseCollector
from functionality.data_collection.collectors.social.hacker_news import HackerNewsCollector
from functionality.data_collection.collectors.web.rss_feed import RssFeedCollector
from interfaces.source_config_interfaces import SourcesConfig

"""
Loads the sources file (sources.yaml) and builds one collector per enabled source.

To add a source:
    - Same type as an existing one (e.g. another RSS feed): just edit sources.yaml
    - New kind of source: write a collector in collectors/web/ or collectors/social/,
      add its settings model to interfaces/source_config_interfaces.py, and wire it
      up in build_collectors() below
"""


class SourcesConfigError(Exception):
    """sources.yaml is missing or invalid. Needs a developer to fix the file - collection cannot start."""


def load_sources_config(path: Path) -> SourcesConfig:
    """Reads and validates the sources file. Raises SourcesConfigError with a readable message on any problem."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))  # safe_load: never executes YAML tags
    except FileNotFoundError as error:
        raise SourcesConfigError(f"Sources file not found at {path}. Create it or set SOURCES_CONFIG_PATH.") from error
    except yaml.YAMLError as error:
        raise SourcesConfigError(f"Sources file {path} is not valid YAML: {error}") from error

    try:
        return SourcesConfig.model_validate(raw or {})
    except ValidationError as error:
        raise SourcesConfigError(f"Sources file {path} failed validation:\n{error}") from error


def build_collectors(config: SourcesConfig) -> list[BaseCollector]:
    """Returns one collector instance per enabled source in the config."""
    web_collectors: list[BaseCollector] = [
        RssFeedCollector(feed) for feed in config.web.rss_feeds if feed.enabled
    ]

    social_collectors: list[BaseCollector] = []
    hacker_news = config.social.hacker_news
    if hacker_news is not None and hacker_news.enabled:
        social_collectors.append(HackerNewsCollector(hacker_news))

    return web_collectors + social_collectors
