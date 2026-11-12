from pathlib import Path

import pytest

from config import SOURCES_CONFIG_PATH
from functionality.data_collection.sources import SourcesConfigError, build_collectors, load_sources_config

"""Tests for loading sources.yaml and building collectors from it."""


VALID_YAML = """
web:
  rss_feeds:
    - key: blog_a
      url: https://a.test/feed
      site_name: Blog A
    - key: blog_b
      url: https://b.test/feed
      site_name: Blog B
      enabled: false
social:
  hacker_news:
    search_url: https://hn.test/api
    item_url_template: https://news.test/item?id={item_id}
"""


def write_yaml(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "sources.yaml"
    path.write_text(content, encoding="utf-8")
    return path


def test_shipped_sources_file_is_valid():
    # Guards against committing a broken sources.yaml
    config = load_sources_config(SOURCES_CONFIG_PATH)
    assert len(build_collectors(config)) > 0


def test_builds_only_enabled_collectors(tmp_path):
    collectors = build_collectors(load_sources_config(write_yaml(tmp_path, VALID_YAML)))
    assert [collector.source_name for collector in collectors] == ["rss:blog_a", "hacker_news"]


def test_disabled_hacker_news_is_not_built(tmp_path):
    yaml_text = VALID_YAML.replace("  hacker_news:\n", "  hacker_news:\n    enabled: false\n")
    collectors = build_collectors(load_sources_config(write_yaml(tmp_path, yaml_text)))
    assert "hacker_news" not in [collector.source_name for collector in collectors]


def test_empty_file_means_no_sources(tmp_path):
    assert build_collectors(load_sources_config(write_yaml(tmp_path, ""))) == []


def test_missing_file_raises_clear_error(tmp_path):
    with pytest.raises(SourcesConfigError, match="not found"):
        load_sources_config(tmp_path / "missing.yaml")


def test_malformed_yaml_raises_clear_error(tmp_path):
    with pytest.raises(SourcesConfigError, match="not valid YAML"):
        load_sources_config(write_yaml(tmp_path, "web: [unclosed"))


@pytest.mark.parametrize("bad_yaml", [
    VALID_YAML.replace("https://a.test/feed", "http://a.test/feed"),     # non-https
    VALID_YAML.replace("site_name: Blog A", "site_nme: Blog A"),          # typo / unknown key
    VALID_YAML.replace("key: blog_b", "key: blog_a"),                     # duplicate key
])
def test_invalid_config_is_rejected(tmp_path, bad_yaml):
    with pytest.raises(SourcesConfigError, match="failed validation"):
        load_sources_config(write_yaml(tmp_path, bad_yaml))
