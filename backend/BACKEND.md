# Tech Trend Spotter — Backend

FastAPI service that collects, processes and serves software/technology trend data.

| Area | Status |
|---|---|
| API skeleton (`/v1/health`) | Done |
| Data collection (web, social and advisory sources) | Initial version done |
| Storage (Postgres): collected items and collection runs | Initial version done |
| API: start/follow collection runs, list items, dashboard stats | Initial version done |
| Data processing, scheduled runs, authentication | Not started |

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

# 5. Create/update the database tables (run again whenever a new migration is added)
python -m database.migrate

# 6. Run the API (docs at http://localhost:8000/docs)
uvicorn main:app --reload
```

| Task | Command |
|---|---|
| Run tests | `pytest` |
| Run tests including the database tests | `TEST_DATABASE_URL=postgresql://... pytest` (see [Tests](#tests)) |
| Apply database migrations | `python -m database.migrate` |
| Run every collector once and print a summary | `python -m functionality.data_collection.collection_core` |

### Environment variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `DATABASE_URL` | Yes | — | Postgres connection string. Without it the data endpoints return 503; `/v1/health` still works |
| `FRONTEND_ORIGINS` | No | `http://localhost:5173` | Comma-separated origins allowed by CORS |
| `COLLECTOR_USER_AGENT` | No | `TechTrendSpotterBot/0.1` | User-Agent sent to sources. Keep it generic: no names or emails |
| `COLLECTOR_TIMEOUT_SECONDS` | No | `10` | Per-request timeout for external sources |
| `SOURCES_CONFIG_PATH` | No | `functionality/data_collection/sources.yaml` | Which sources file to load (e.g. a different file per environment) |
| `GITHUB_TOKEN` | No | — | Raises the GitHub Advisories rate limit from 60 to 5,000 requests/hour. Use a fine-grained token with **no** permissions (the data is public). Never logged |
| `COLLECTION_RUN_COOLDOWN_SECONDS` | No | `300` | Minimum time between collection runs started through the API |
| `TEST_DATABASE_URL` | No | — | Only for tests: enables the database integration tests (they use a throwaway schema) |

---

## Project layout

```
backend/
├── main.py                     # FastAPI app, CORS, error handlers, router registration (everything under /v1)
├── config.py                   # Every environment variable is read here
├── app_logging.py              # Structured JSON logger
├── endpoints/                  # API routers, dependencies and the error envelope (errors.py)
├── interfaces/                 # Pydantic contracts shared between modules
│   ├── api_interfaces.py            # Public API contract: envelopes, items, stats, runs
│   ├── collection_interfaces.py     # Collected data schema (WebArticle, SocialPost, Advisory, CollectionResult)
│   ├── source_config_interfaces.py  # Schema for sources.yaml
│   └── query_interfaces.py          # Health response
├── functionality/
│   ├── data_collection/        # See "Data collection" below
│   ├── storage/                # SQL for collected_items and collection_runs (repositories)
│   └── collection_runs/        # Starts runs and records their outcome
├── database/
│   ├── connection.py           # Connection pool (lazy, statement timeout, 503 when unreachable)
│   ├── migrate.py              # Migration runner: python -m database.migrate
│   └── migrations/             # Numbered .sql files, applied in order, each once
└── tests/                      # Mirrors the source tree; fakes.py holds in-memory stand-ins
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
           (WebArticle[], SocialPost[] or Advisory[], never mixed)
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
| `collectors/advisory/cisa_kev.py` | CISA Known Exploited Vulnerabilities catalog (JSON feed, no key needed) → `Advisory` |
| `collectors/advisory/github_advisories.py` | GitHub-reviewed security advisories (REST API, optional token, paginated) → `Advisory` |
| `http_client.py` | `SourceHttpClient`: the only way collectors make HTTP requests |
| `collection_core.py` | `run_collection()`: runs all collectors concurrently, one result per source |

### Standard schema

Defined in `interfaces/collection_interfaces.py`. data_processing should depend only on these models and never on a specific collector.

**Fields on every item (`CollectedItem`)**

| Field | Notes |
|---|---|
| `item_id` | SHA-256 of `source_name:external_id`. The same item gets the same ID on every run, so duplicates can be removed |
| `source_type` | `"web"`, `"social"` or `"advisory"` |
| `source_name` | e.g. `rss:krebsonsecurity`, `hacker_news`, `cisa_kev` |
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
| `Advisory` (`source_type="advisory"`) | `cve_id`, `affected` (list of `AffectedProduct`: `vendor`, `product`, `ecosystem`), `severity` (`low`/`medium`/`high`/`critical`), `known_exploited`, `known_ransomware_use`, `remediation_due_date` |

`Advisory` is one record per vulnerability, even when it affects several products, so a vulnerability is never counted twice when spotting trends. `affected` says who is affected, which is the main input for finding potential clients. Fields a source doesn't provide are null. For example, CISA KEV has no severity rating and no ecosystem. `known_exploited=False` means "not confirmed", not "safe".

CISA KEV mapping notes:
- `published_at` is the date CISA **added** the entry to the catalog, not the CVE's original publication date.
- `url` links to the CVE's NVD page.
- `tags` holds the CWE IDs.

GitHub Advisories mapping notes:
- Only GitHub-reviewed advisories are collected. Withdrawn advisories are dropped.
- `external_id` is the GHSA ID. `cve_id` is null when GitHub hasn't linked a CVE.
- `affected` has one entry per package (no vendor: open-source packages don't have one). Version ranges stay in `raw_payload`.
- GitHub's `unknown` severity becomes null.
- Reporter usernames (`credits`) are removed from `raw_payload`.
- Results come in pages of 100 (about 4 days' worth). The collector follows the `Link` header up to `max_pages`, and logs a warning if it stops early. It only follows next-page links on the configured host, so the token can't be sent anywhere else.
- Without `GITHUB_TOKEN`, GitHub allows 60 requests/hour. Going over returns 403, and the run fails as `non_retryable`. Set the token if that happens.

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

advisory:
  cisa_kev:
    feed_url: https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json
    lookback_days: 30                 # 1–3650; only entries added in the last N days
  github_advisories:
    api_url: https://api.github.com/advisories
    lookback_days: 7                  # 1–365; only advisories published in the last N days
    max_pages: 10                     # 1–30; pages of 100 advisories per run
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
  2. Create a collector in `collectors/web/`, `collectors/social/` or `collectors/advisory/` that extends `BaseCollector` and implements:
     - `fetch_records()`: makes the network calls through `SourceHttpClient`. Raises `FetchError` or `SourceFormatError` on failure.
     - `parse_record()`: converts one raw record into a `WebArticle`, `SocialPost` or `Advisory`.
  3. Add the collector in `build_collectors()` in `sources.py`.
  4. Add tests under `tests/functionality/data_collection/collectors/`, using `httpx.MockTransport` instead of real network calls.

### Tests

Run `pytest` from `backend/`. All tests are deterministic and make no network calls; HTTP is mocked with `httpx.MockTransport`. API and service tests use the in-memory fakes in `tests/fakes.py`.

The database tests (`tests/database/`) are skipped unless `TEST_DATABASE_URL` is set. Each run creates its own throwaway schema, migrates it and drops it afterwards, so it's safe to point at your development database:

```bash
TEST_DATABASE_URL=postgresql://techtrendspotter:techtrendspotter@localhost:5432/techtrendspotter pytest
```

| Test file | Covers |
|---|---|
| `test_http_client.py` | Retry rules, timeouts, circuit breaker, robots.txt, invalid JSON, pagination links, per-request headers |
| `test_collection_core.py` | Failure isolation, run time limits, shared correlation ID |
| `test_sources.py` | Loading and validating config, enabled/disabled sources; also checks the shipped `sources.yaml` is valid |
| `collectors/web/test_rss_feed.py` | Feed parsing, HTML sanitisation, stable IDs, truncation, invalid config |
| `collectors/social/test_hacker_news.py` | Parsing hits, removing personal data, configured URLs and thresholds, invalid config |
| `collectors/advisory/test_cisa_kev.py` | Parsing entries, lookback window, ransomware mapping, skipping bad records, CVE ID validation, invalid config |
| `collectors/advisory/test_github_advisories.py` | Parsing, multi-package advisories, removing personal data, severity mapping, withdrawn advisories, pagination and page cap, refusing off-host links, token handling (sent only when set, never logged), invalid config |
| `storage/test_items_repository.py` | Plain-text summaries, cursor encoding and tamper rejection, filling empty days, what goes into `details` |
| `collection_runs/test_run_service.py` | One active run, cool-down, per-source results, new-item counts, failures recorded without leaking details |
| `endpoints/test_api.py` | Envelopes, status codes (400/404/409/429/503/500), validation, background run flow |
| `database/test_repositories_db.py` | Real SQL: migration, upsert and de-duplication, pagination, stats, run lifecycle (needs `TEST_DATABASE_URL`) |

---

## Storage

Postgres tables, created by `database/migrations/001_collected_items_and_runs.sql`:

| Table | Holds |
|---|---|
| `collected_items` | Every item ever collected, one row per `item_id`. Common fields are columns; type-specific fields (score, severity, `affected`...) are in the `details` JSONB column, so a new item type doesn't need a migration. `raw_payload` keeps the original record. `first_collected_at` / `last_collected_at` track when it was seen |
| `collection_runs` | One row per run: status, timings, item counts and the outcome of each source |
| `schema_migrations` | Which migration files have been applied |

Rules:
- **Migrations are a separate step** (`python -m database.migrate`), never run by the API. Never edit an applied migration; add a new numbered file.
- **Re-collecting an item updates it** (content, tags, `last_collected_at`) but keeps `first_collected_at`. A run reports how many items were new.
- **Only one run can be active at a time.** A unique partial index enforces this in the database, so two simultaneous requests can't both start a run.
- **Runs interrupted by a restart** are marked failed when the API starts, so they never block new runs.
- **Every query is parameterised and has a `LIMIT`**. Every connection has a 10s statement timeout.
- **If Postgres is down**, the API still starts. Data endpoints return 503 with a readable message, and `/v1/health` keeps answering.

---

## API

Every route is under `/v1`. Interactive docs: http://localhost:8000/docs. The contract is in `interfaces/api_interfaces.py`.

| Endpoint | Purpose |
|---|---|
| `GET /health` | API is up (doesn't touch the database) |
| `GET /items` | Collected items, newest first. Filters: `source_type`, `source_name`. Cursor pagination: `limit` (1–100, default 25) and `cursor` |
| `GET /item-stats` | Dashboard figures: totals per source, items per day, advisory severity, exploited count, most affected vendors and ecosystems. `days` (1–90, default 14) |
| `POST /collection-runs` | Starts a run in the background and returns it straight away (`202`). `409` if one is already running, `429` + `Retry-After` during the cool-down |
| `GET /collection-runs/latest` | The most recent run (`404 no_runs` if there has never been one) |
| `GET /collection-runs/{run_id}` | One run, for polling until it's `completed` or `failed` |

**Response envelopes**, used by every endpoint:

```jsonc
{"data": {...}}                                                     // one resource
{"data": [...], "pagination": {"next_cursor": "...", "limit": 25}}  // a list
{"error": {"code": "invalid_cursor", "message": "..."}}             // any error
```

- Every item has the same shape. Fields that don't apply to its type are `null` (e.g. `score` on an advisory).
- Items return a plain-text `summary` (HTML removed, max 300 characters), not the full content or the raw payload.
- Error messages are written for the person using the dashboard: what went wrong and what to do. Internal details only go to the logs.
- A run that completes can still have failed sources. Check `sources[].status`. A `failed` run means the run as a whole couldn't finish.

**Authentication: none yet.** Every endpoint is public. `POST /collection-runs` is limited to one run at a time with a cool-down, so it can't be used to hammer the sources. Add authentication before deploying anywhere public.

---

## Next steps

1. Authentication before any public deployment.
2. Scheduled collection runs (e.g. hourly), reusing `CollectionRunService`.
3. More collectors: OSV/NVD, Reddit, Mastodon.
4. The data_processing module (enrichment, trend detection).
