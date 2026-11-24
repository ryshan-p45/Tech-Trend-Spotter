# Tech Trend Spotter

Tech Trend Spotter scans public sources for emerging trends in software and technology, such as newly exploited vulnerabilities, fast-growing discussions, and new security advisories. It then turns those trends into business opportunities for a software consultancy: potential clients and partners, services to offer, and topics for marketing content.

It works the way an analyst spots investment opportunities: it follows signals across many sources and connects them to something you can act on.

```
collect → store → enrich → detect trends/categorise → match opportunities → dashboard / alerts
```

## Status

| Area | Status |
|---|---|
| [Backend API](#backend-api) | Done (skeleton and health check) |
| [Frontend](#frontend) | Done (setup, theme, placeholder dashboard) |
| [Local database](#local-database) | Postgres container ready; schema not started |
| [Data collection](#data-collection) | Done: RSS feeds, Hacker News, CISA KEV, GitHub Security Advisories |
| Storage of collected items | Not started |
| Enrichment, trend detection, opportunity matching | Not started |
| Real dashboard, alerts, Railway deployment | Not started |

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
uvicorn main:app --reload          # http://localhost:8000

# 3. Frontend (from frontend/, in a second terminal)
cd frontend
cp .env.example .env
npm install
npm run dev                        # http://localhost:5173
```

When the dashboard shows **API online**, the frontend and backend are connected.

| Task | Command |
|---|---|
| Backend tests | `pytest` (from `backend/`) |
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

A FastAPI service that everything else is built on.

- Every route is versioned under `/v1`.
- `GET /v1/health` returns `{"status": "ok"}`. Railway and the frontend use it to check the API is up.
- CORS only allows the frontend origins listed in `FRONTEND_ORIGINS`.
- All settings come from environment variables, read in one place: `backend/config.py`. Nothing secret is hardcoded. `backend/.env.example` lists every variable.
- Logs are structured JSON lines with a UTC timestamp, level, service name and correlation ID.

## Frontend

A React + TypeScript app built with Vite. So far it has the base the real dashboard will sit on, not the dashboard itself.

- **Routing** (React Router) with a single page for now: the dashboard at `/`.
- **API client** (`src/api/client.ts`): a small wrapper around `fetch` that calls the `/v1` API. Set the backend URL with `VITE_API_BASE_URL`, so local and deployed builds can use different backends.
- **Server data** is fetched and cached with TanStack Query.
- **Cyber/HUD theme**: dark navy with cyan, teal and magenta accents and a monospace font. The colours are defined once as Tailwind tokens in `src/index.css`, e.g. `bg-hud-bg` and `text-hud-cyan`. The look is based on [plans/graphic_inspiration](plans/graphic_inspiration).
- **Placeholder dashboard**: shows whether the backend can be reached, with loading and error messages.
- Charting (ECharts) and network-graph (react-force-graph) libraries are installed for the upcoming trend views.
- Tests run with Vitest and Testing Library.

## Local database

`docker-compose.yml` runs a PostgreSQL 17 container for local development. It reads its user, password and database name from `backend/.env`, and keeps data in a Docker volume between restarts. The backend connects through `DATABASE_URL`. The database schema and writes are the next stage of the pipeline.

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

1. An OSV/NVD collector, to finish the advisory sources.
2. A Postgres schema, and writing collected items to it.
3. Running collection on a schedule.
4. Enrichment: pulling companies, products, technologies and CVEs out of each item.
5. Trend detection and opportunity matching.
6. The real dashboard, with a network graph of linked trends.

## Development guidelines

The rules for coding, architecture, data, security, evaluation and API design are in [context/](context/). Read them before contributing. Apply each rule only where it's relevant, and keep things simple.
