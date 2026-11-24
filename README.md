# Tech Trend Spotter

Tech Trend Spotter scans public sources for emerging trends in software and technology, such as newly exploited vulnerabilities, fast-growing discussions, and new security advisories. It then turns those trends into business opportunities for a software consultancy: potential clients and partners, services to offer, and topics for marketing content.

It works the way an analyst spots investment opportunities: it follows signals across many sources and connects them to something you can act on.

```
collect → store → enrich → detect trends/categorise → match opportunities → dashboard / alerts
```

## Status

| Area | Status |
|---|---|
| [Backend API](#backend-api) | Done: health, items, dashboard stats, collection runs |
| [Data collection](#data-collection) | Done: RSS feeds, Hacker News, CISA KEV, GitHub Security Advisories |
| [Storage](#storage) | Done: collected items and collection runs in Postgres |
| [Dashboard](#dashboard) | Done: HUD dashboard of collected data, with on-demand collection runs |
| Enrichment, trend detection, opportunity matching | Not started |
| Scheduled runs, authentication, alerts, Railway deployment | Not started |

The full plan, open questions and to-do list are in [plans/Ideas.md](plans/Ideas.md).

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python, FastAPI, Pydantic, httpx |
| Frontend | React, TypeScript, Vite, Tailwind CSS, TanStack Query |
| Database | PostgreSQL (Docker locally) |
| Hosting (planned) | Railway |

## Getting started

You need Python 3, Node.js and Docker.

```bash
# 1. Start Postgres (from the repo root)
cp backend/.env.example backend/.env
docker compose up -d

# 2. Backend (from backend/)
cd backend
python3 -m venv code_env
source code_env/bin/activate
pip install -r requirements-dev.txt
python -m database.migrate         # create the tables (re-run after pulling new migrations)
uvicorn main:app --reload          # http://localhost:8000 (API docs at /docs)

# 3. Frontend (from frontend/, in a second terminal)
cd frontend
cp .env.example .env
npm install
npm run dev                        # http://localhost:5173
```

When the dashboard shows **API online**, the frontend and backend are connected. Press **Run collection** to fetch the first data.

| Task | Command |
|---|---|
| Backend tests | `pytest` (from `backend/`). Set `TEST_DATABASE_URL` to also run the database tests |
| Frontend tests | `npm test` (from `frontend/`) |
| Frontend lint | `npm run lint` (from `frontend/`) |
| Run every collector once and print a summary | `python -m functionality.data_collection.collection_core` (from `backend/`) |

## Repository layout

```
.
├── backend/            # FastAPI service: API and data collection (see backend/BACKEND.md)
├── frontend/           # React dashboard
├── context/            # Development guidelines: coding, architecture, data, security, evaluation, API
├── plans/              # Product ideas, pipeline plan and design inspiration
└── docker-compose.yml  # Local Postgres
```

---

## Backend API

A FastAPI service that everything else is built on. Every route is versioned under `/v1`, and interactive docs are at `/docs`.

| Endpoint | Purpose |
|---|---|
| `GET /v1/health` | Checks the API is up (used by Railway and the dashboard) |
| `GET /v1/items` | Collected items, newest first, filterable by source type or source, with cursor pagination |
| `GET /v1/item-stats` | Dashboard figures: totals, items per day, advisory severity, exploited count, most affected vendors and ecosystems |
| `POST /v1/collection-runs` | Starts a collection run in the background and returns it at once (`202`) |
| `GET /v1/collection-runs/latest`, `GET /v1/collection-runs/{run_id}` | Follow a run until it completes |

- Every response uses one envelope: `{"data": ...}`, with `pagination` added for lists, or `{"error": {"code", "message"}}`. Error messages say what went wrong and what to do next.
- Only one collection run can be active at a time, and there's a cool-down between runs (default 5 minutes), so the button can't hammer external sources.
- **There is no authentication yet.** Add it before deploying anywhere public.
- CORS only allows the frontend origins listed in `FRONTEND_ORIGINS`.
- All settings come from environment variables, read in one place: `backend/config.py`. Nothing secret is hardcoded. `backend/.env.example` lists every variable.
- Logs are structured JSON lines with a UTC timestamp, level, service name and correlation ID. A collection run's ID is its correlation ID.

## Storage

Collected items and collection runs are stored in PostgreSQL. `docker-compose.yml` runs a PostgreSQL 17 container for local development, and the backend connects through `DATABASE_URL`.

- Tables are created by versioned migrations (`python -m database.migrate`). This is a separate step; the API never runs migrations.
- Items are de-duplicated by their stable ID. Collecting an item again refreshes it but keeps when it was first seen, so each run knows how many items were new.
- Each run records its status, timings and the outcome of every source.
- If the database is down, the API still starts. Data endpoints return a clear 503, and the health check keeps working.

## Dashboard

A React + TypeScript app (Vite, Tailwind CSS, TanStack Query, ECharts), styled as a cyber/HUD interface after [plans/graphic_inspiration](plans/graphic_inspiration): dark navy panels with glowing corner brackets, striped headings, and cyan and magenta accents.

- **Run collection** starts a run, shows its progress live, and refreshes the dashboard when it finishes.
- **Headline figures:** items collected, advisories, vulnerabilities exploited in the wild, and critical or high advisories.
- **Activity chart:** items per day by source type, with a table view.
- **Exposure:** share of advisories exploited in the wild, and advisories by severity.
- **Most affected vendors and package ecosystems.**
- **Latest signals:** a feed of every item with tabs for advisories, news and discussions. Advisories show their CVE, severity, exploitation flags and affected products.
- **Exploited in the wild:** the newest CISA KEV entries with their fix deadlines.
- **Sources:** whether each source worked in the last run, and why one failed.

Every panel has loading, empty and error states written in plain language. Chart colours were checked for colour-blind safety and contrast. Severity is never shown by colour alone, and only `http(s)` links from collected data are rendered. See [frontend/FRONTEND.md](frontend/FRONTEND.md) for details.

## Data collection

The first stage of the pipeline. Collectors pull recent items from public sources and convert them into one standard format, so the later stages never need to know where an item came from. Every source is free. Only GitHub takes an optional token, for a higher rate limit.

### Sources

| Source | Type | What it provides |
|---|---|---|
| RSS/Atom feeds (Krebs on Security, BleepingComputer, The GitHub Blog) | `web` | Security and tech news articles |
| Hacker News (Algolia API) | `social` | Popular stories with points and comment counts |
| CISA Known Exploited Vulnerabilities | `advisory` | Vulnerabilities confirmed to be exploited in the wild, naming the affected vendor and product |
| GitHub Security Advisories | `advisory` | Reviewed vulnerabilities in open-source packages, with severity and affected packages per ecosystem |

Sources are listed in `backend/functionality/data_collection/sources.yaml`. That file is the only place they're configured, and it acts as an allowlist. To add another RSS feed, add an entry there; no code changes are needed. The file is checked when it's loaded: URLs must be https, and unknown keys or out-of-range values stop startup with a clear error.

### The standard format

Every item has the same core fields: a stable ID (the same item gets the same ID on every run, so duplicates can be removed), title, link, content, tags, publish and collection times, and the original record. Each source type then adds its own fields:

| Item type | Extra fields |
|---|---|
| `WebArticle` | Publisher name |
| `SocialPost` | Score, comment count, discussion link |
| `Advisory` | CVE ID, affected products (vendor, product, ecosystem), severity, whether it's known to be exploited, ransomware use, and the deadline for applying a fix |

An advisory stays one item even when it affects several products, so a vulnerability isn't counted twice when spotting trends.

### Reliability and safety

- Every request has a timeout. Temporary failures (timeouts, 429, 5xx) are retried with exponential backoff; other errors are not.
- Each host has a circuit breaker: after repeated failures, it's skipped for a cool-down period.
- One failing or slow source never stops the others. Each run returns a result per source, marked `success` or `failed` with the reason.
- Records that don't fit the format are skipped and counted, not fatal.
- robots.txt is respected for websites, and responses over 5 MB are rejected.
- Personal data is removed: Hacker News usernames and GitHub advisory reporter names are not kept.
- Tests make no network calls. All HTTP is mocked.

See [backend/BACKEND.md](backend/BACKEND.md) for the full schema, configuration options, and how to add a new kind of source.

---

## Next up

1. Authentication, before any public deployment.
2. Running collection on a schedule.
3. An OSV/NVD collector, to finish the advisory sources.
4. Enrichment: pulling companies, products, technologies and CVEs out of each item.
5. Trend detection and opportunity matching.
6. A network graph of linked trends on the dashboard (needs enrichment first).

## Development guidelines

The rules for coding, architecture, data, security, evaluation and API design are in [context/](context/). Read them before contributing. Apply each rule only where it's relevant, and keep things simple.
