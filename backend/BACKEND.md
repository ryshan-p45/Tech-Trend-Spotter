# Tech Trend Spotter — Backend

FastAPI service that collects, processes and serves software/technology trend data.

| Area | Status |
|---|---|
| API skeleton (`/v1/health`) | Done |
| Data collection (web + social sources) | Initial version done |
| Storage (Postgres) | Container set up; schema and writes not started |
| Data processing, scheduling, collection endpoints | Not started |

---

## Getting started

All commands run from the `backend/` directory.

```bash
# 1. Create and activate the virtual environment
python3 -m venv code_env
source code_env/bin/activate

# 2. Install dependencies (requirements-dev.txt adds pytest on top of requirements.txt)
pip install -r requirements-dev.txt

# 3. Configure environment variables
cp .env.example .env

# 4. Start Postgres (from the repository root)
docker compose up -d

# 5. Run the API
uvicorn main:app --reload
```

| Task | Command |
|---|---|
| Run tests | `pytest` |
| Run every collector once and print a summary | `python -m functionality.data_collection.collection_core` |

### Environment variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `DATABASE_URL` | Yes (once storage exists) | — | Postgres connection string |
| `FRONTEND_ORIGINS` | No | `http://localhost:5173` | Comma-separated origins allowed by CORS |
| `COLLECTOR_USER_AGENT` | No | `TechTrendSpotterBot/0.1` | User-Agent sent to sources. Keep it generic: no names or emails |
| `COLLECTOR_TIMEOUT_SECONDS` | No | `10` | Per-request timeout for external sources |
| `SOURCES_CONFIG_PATH` | No | `functionality/data_collection/sources.yaml` | Which sources file to load (e.g. a different file per environment) |

---

## Project layout

```
backend/
├── main.py                     # FastAPI app, CORS, router registration (everything under /v1)
├── config.py                   # Every environment variable is read here
├── app_logging.py              # Structured JSON logger
├── endpoints/                  # API routers
├── interfaces/                 # Pydantic contracts shared between modules
│   ├── collection_interfaces.py     # Collected data schema (WebArticle, SocialPost, CollectionResult)
│   ├── source_config_interfaces.py  # Schema for sources.yaml
│   └── query_interfaces.py          # API response models
├── functionality/
│   └── data_collection/        # See "Data collection" below
├── database/                   # DB schema (db_schema.dbml)
└── tests/                      # Mirrors the source tree
```

Imports are written relative to `backend/` (e.g. `from config import ...`). `pytest.ini` sets `pythonpath = .` so tests resolve them the same way.

---

## Data collection

Fetches raw items from configured sources and returns them in a single standard format, ready for the (future) data_processing module.

### Libraries

| Library | Used for |
|---|---|
| **httpx** | Async HTTP client for every request |
| **feedparser** | Parsing RSS/Atom feeds; also strips unsafe HTML from summaries |
| **tenacity** | Retries with exponential backoff |
| **pyyaml** | Loading `sources.yaml` (with `safe_load`, which never executes YAML tags) |
| `urllib.robotparser` (Python standard library) | robots.txt checks for websites |

Almost every planned source (Hacker News, Reddit, Mastodon, GitHub Advisories, CISA KEV, NVD/OSV, RSS) has a free public API or feed, so a crawling framework such as Scrapy or Playwright isn't needed. If a source with neither turns up, add `selectolax` for HTML parsing, and Playwright only for pages rendered with JavaScript.

### Data flow

```
sources.yaml ──► sources.py ──► collectors ──► SourceHttpClient ──► external source
 (what to       (validate,      (fetch +        (timeouts, retries,
  collect)       build)          parse)          circuit breaker, robots.txt)
                                   │
                                   ▼
                     CollectionResult per source
                 (WebArticle[] or SocialPost[], never mixed)
                                   │
                                   ▼
                     data_processing / storage (next)
```

| File | Responsibility |
|---|---|
| `sources.yaml` | Allowlist of sources with their URLs and settings. The only place sources are configured |
| `sources.py` | Loads and validates `sources.yaml`, then builds one collector per enabled source |
| `collectors/base.py` | `BaseCollector`: run time limit, error isolation, skips records that don't fit the schema |
| `collectors/web/rss_feed.py` | RSS/Atom feeds → `WebArticle` |
| `collectors/social/hacker_news.py` | Hacker News (Algolia API, no key needed) → `SocialPost` |
| `http_client.py` | `SourceHttpClient`: the only way collectors make HTTP requests |
| `collection_core.py` | `run_collection()`: runs all collectors concurrently, one result per source |

### Standard schema

Defined in `interfaces/collection_interfaces.py`. data_processing should depend only on these models and never on a specific collector.

**Fields on every item (`CollectedItem`)**

| Field | Notes |
|---|---|
| `item_id` | SHA-256 of `source_name:external_id`. The same item gets the same ID on every run, so duplicates can be removed |
| `source_type` | `"web"` or `"social"` |
| `source_name` | e.g. `rss:krebsonsecurity`, `hacker_news` |
| `external_id` | The item's ID at the source |
| `title` | Required, at most 500 characters |
| `url` | Nullable (e.g. Ask HN posts have no link) |
| `content` | Nullable; truncated to 20,000 characters rather than rejected |
| `tags` | Tags provided by the source |
| `published_at` / `collected_at` | Timezone-aware UTC datetimes |
| `raw_payload` | The original record, stored as plain JSON, so new fields can be extracted later without collecting again. Personal data (e.g. HN usernames) is removed |

**Extra fields by type**

| Model | Extra fields |
|---|---|
| `WebArticle` (`source_type="web"`) | `site_name` |
| `SocialPost` (`source_type="social"`) | `score`, `comment_count`, `discussion_url` |

**`CollectionResult`** has the same shape whether the run succeeded or failed:

| Field | Notes |
|---|---|
| `correlation_id` | Shared by every collector in the same run |
| `source_name`, `source_type` | Which collector produced the result |
| `status` | `"success"` or `"failed"` |
| `items` | Empty on failure |
| `skipped_count` | Records dropped because they failed validation |
| `error` | Null on success. On failure, `category` (`retryable` or `non_retryable`) and `message` |
| `started_at`, `finished_at` | UTC |

### Reliability and safety

| Concern | Behaviour |
|---|---|
| Timeouts | Every request times out after `COLLECTOR_TIMEOUT_SECONDS`. Each collector run has a total limit (`run_timeout_seconds`, default 120s) |
| Retries | Up to 3 attempts with exponential backoff, only for retryable errors (timeouts, connection errors, 429, 5xx). Other 4xx errors fail immediately |
| Circuit breaker | Each host gets its own. After 5 consecutive failures, that host is skipped for 5 minutes |
| robots.txt | Checked for websites (RSS feeds) but not for documented APIs. If robots.txt is missing (4xx), everything is allowed. If it can't be reached (5xx or network error), nothing is allowed (RFC 9309) |
| Response size | Responses over 5 MB are rejected |
| Isolation | A failing or hanging collector returns a `failed` result. The others are unaffected |
| Bad records | Records that don't fit the schema are skipped, counted in `skipped_count` and logged |
| Logging | JSON lines containing a UTC timestamp, level, service and `correlation_id`. Every external request logs its URL, status and duration |

The circuit breaker and robots.txt cache are kept in memory for one run only. Move them to the database if collection is ever split across several workers.

### Configuring sources

Edit `functionality/data_collection/sources.yaml`:

```yaml
web:
  rss_feeds:
    - key: krebsonsecurity            # slug, becomes source_name "rss:krebsonsecurity"
      url: https://krebsonsecurity.com/feed/
      site_name: Krebs on Security
      enabled: true                   # optional, defaults to true

social:
  hacker_news:
    search_url: https://hn.algolia.com/api/v1/search_by_date
    item_url_template: https://news.ycombinator.com/item?id={item_id}
    min_points: 50                    # 0 or more
    max_items: 50                     # 1–100
```

The file is validated on load. The following stop startup with a readable `SourcesConfigError`:

- a URL that isn't https
- an unknown key (catches typos)
- two RSS feeds with the same `key`
- a value out of range
- a missing file, or invalid YAML

### Adding a source

- **Another source of an existing type** (e.g. a new RSS feed): add an entry to `sources.yaml`. No code changes.
- **A new kind of source** (e.g. Reddit):
  1. Add a settings model to `interfaces/source_config_interfaces.py` and a matching section to `sources.yaml`.
  2. Create a collector in `collectors/web/` or `collectors/social/` that extends `BaseCollector` and implements:
     - `fetch_records()`: makes the network calls through `SourceHttpClient`. Raises `FetchError` or `SourceFormatError` on failure.
     - `parse_record()`: converts one raw record into a `WebArticle` or `SocialPost`.
  3. Add the collector in `build_collectors()` in `sources.py`.
  4. Add tests under `tests/functionality/data_collection/collectors/`, using `httpx.MockTransport` instead of real network calls.

### Tests

Run `pytest` from `backend/`. All tests are deterministic and make no network calls; HTTP is mocked with `httpx.MockTransport`.

| Test file | Covers |
|---|---|
| `test_http_client.py` | Retry rules, timeouts, circuit breaker, robots.txt, invalid JSON |
| `test_collection_core.py` | Failure isolation, run time limits, shared correlation ID |
| `test_sources.py` | Loading and validating config, enabled/disabled sources; also checks the shipped `sources.yaml` is valid |
| `collectors/web/test_rss_feed.py` | Feed parsing, HTML sanitisation, stable IDs, truncation, invalid config |
| `collectors/social/test_hacker_news.py` | Parsing hits, removing personal data, configured URLs and thresholds, invalid config |

---

## Next steps

1. Postgres schema and storage for collected items, with de-duplication by `item_id`.
2. More collectors: GitHub Security Advisories, CISA KEV, OSV/NVD, Reddit, Mastodon.
3. Scheduled collection runs.
4. An endpoint that starts a run and returns a job ID, plus an endpoint to check its status.
5. The data_processing module.
