"""
Data collection functionality requirements:
- Open source and safe web-scraping library or framework
- Should feed into a data_processing Module that will handle transformation of raw data
    into useful insights that can be stored as well for tracking over time
- Web-scraping and social media scraping should be done. But sources shouldn't mix so data can be handled differently
- There needs to be some kind of standard format/schema for data so that enough fields are filled to be useful (this should be defined early)
- Changing one component or module shouldn't affect others (decoupled) but still integrated (so extendible)

Library decision:
- httpx (BSD)        - async HTTP client for every request. Almost all planned sources
                        (Hacker News, Reddit, Mastodon, GitHub Advisories, CISA KEV, NVD/OSV, RSS)
                        expose free public APIs or feeds, so a full crawling framework
                        (Scrapy, Playwright) would be unnecessary weight.
- feedparser (BSD)   - parses RSS/Atom feeds and sanitises their HTML.
- tenacity (Apache)  - retries with exponential backoff.
- Stdlib urllib.robotparser - robots.txt checks for websites.
- Later, only if a source has no API/feed: add selectolax for HTML parsing, and
    Playwright only for JavaScript-rendered pages.

How the pieces fit (data flow):
    sources.yaml         -> which sources to collect, with their URLs and settings (allowlist)
    sources.py           -> loads/validates sources.yaml and builds the collectors
    collectors/web/      -> web sources    -> WebArticle items
    collectors/social/   -> social sources -> SocialPost items
    http_client.py       -> shared polite HTTP (timeouts, retries, circuit breaker, robots.txt)
    interfaces/collection_interfaces.py -> the standard schema data_processing consumes
    collection_core.py   -> runs all collectors concurrently and returns one CollectionResult per source

Usage (manual run from the backend/ directory):
    python -m functionality.data_collection.collection_core
"""

import asyncio
import uuid

import httpx

from app_logging import get_logger
from config import COLLECTOR_TIMEOUT_SECONDS, COLLECTOR_USER_AGENT, SOURCES_CONFIG_PATH
from functionality.data_collection.collectors.base import BaseCollector
from functionality.data_collection.http_client import SourceHttpClient
from functionality.data_collection.sources import build_collectors, load_sources_config
from interfaces.collection_interfaces import CollectionResult


logger = get_logger("data_collection")


def build_http_client() -> httpx.AsyncClient:
    """Creates the shared httpx client with our User-Agent, timeout and redirect limits."""
    return httpx.AsyncClient(
        headers={"User-Agent": COLLECTOR_USER_AGENT},
        timeout=httpx.Timeout(COLLECTOR_TIMEOUT_SECONDS),
        follow_redirects=True,
        max_redirects=5,
    )


async def run_collection(collectors: list[BaseCollector], correlation_id: str | None = None,
                         client: httpx.AsyncClient | None = None) -> list[CollectionResult]:
    """
    Runs every collector concurrently and returns one CollectionResult per collector.

    - A failing collector produces a 'failed' result; the others are unaffected.
    - `client` can be injected (e.g. a mocked transport in tests); otherwise one is created and closed here.
    """
    correlation_id = correlation_id or str(uuid.uuid4())
    logger.info("Collection run started", extra={
        "correlation_id": correlation_id,
        "context": {"collectors": [collector.source_name for collector in collectors]},
    })

    owns_client = client is None
    http_client = client or build_http_client()
    try:
        source_http = SourceHttpClient(http_client)
        results = await asyncio.gather(*(collector.collect(source_http, correlation_id) for collector in collectors))
    finally:
        if owns_client:
            await http_client.aclose()

    logger.info("Collection run finished", extra={
        "correlation_id": correlation_id,
        "context": {
            "succeeded": sum(1 for result in results if result.status == "success"),
            "failed": sum(1 for result in results if result.status == "failed"),
            "items": sum(len(result.items) for result in results),
        },
    })
    return list(results)


async def _manual_run() -> None:
    """Runs all collectors configured in sources.yaml once and prints a short summary per source."""
    collectors = build_collectors(load_sources_config(SOURCES_CONFIG_PATH))
    results = await run_collection(collectors)
    for result in results:
        print(f"{result.source_type:7} {result.source_name:24} {result.status:8} "
              f"items={len(result.items):<4} skipped={result.skipped_count}"
              + (f"  error={result.error.message}" if result.error else ""))


if __name__ == "__main__":
    asyncio.run(_manual_run())
