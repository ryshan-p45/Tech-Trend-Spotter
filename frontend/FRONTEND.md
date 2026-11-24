# Tech Trend Spotter — Frontend

The dashboard for Tech Trend Spotter: React + TypeScript, built with Vite, styled as a cyber/HUD interface (see [plans/graphic_inspiration](../plans/graphic_inspiration)).

## Getting started

Run from `frontend/`. The backend must be running (see [backend/BACKEND.md](../backend/BACKEND.md)).

```bash
cp .env.example .env     # VITE_API_BASE_URL=http://localhost:8000
npm install
npm run dev              # http://localhost:5173
```

| Task | Command |
|---|---|
| Dev server | `npm run dev` |
| Tests | `npm test` |
| Lint | `npm run lint` |
| Production build | `npm run build` |

## What the dashboard shows

| Area | What it shows | Data from |
|---|---|---|
| Header | API status, **Run collection** button, and what the last run did | `/health`, `/collection-runs` |
| Headline figures | Items collected (all time), and for the last 14 days: advisories, exploited in the wild, critical or high | `/item-stats` |
| Activity | Items per day, stacked by source type, with a "View as table" option | `/item-stats` |
| Exposure | Share of advisories exploited in the wild, and advisories by severity | `/item-stats` |
| Most affected vendors / ecosystems | Vendors and package ecosystems named most often in advisories | `/item-stats` |
| Latest signals | Every item, newest first, with tabs (All, Advisories, News, Discussions) and **Load more** | `/items` |
| Exploited in the wild | Newest CISA KEV entries, with affected product and fix deadline | `/items?source_name=cisa_kev` |
| Sources | Whether each source worked in the last run, and why one failed | `/collection-runs/latest` |

**Running a collection.** The button starts a run, then the dashboard checks on it every 2 seconds. When the run finishes, every panel refreshes. If a run is already going, the dashboard follows that one. If runs are on cool-down, it says how long to wait.

Every panel has a loading message, an empty state that says how to get data, and an error state that shows the API's plain-language message. If the API can't be reached at all, a single message with a **Try again** button replaces the panels.

## Code layout

```
src/
├── api/
│   ├── types.ts          # Mirror of the backend API contract (keep in sync with api_interfaces.py)
│   └── client.ts         # fetch wrapper: parses the envelope, throws ApiError with the API's message
├── components/           # Panels and widgets (Panel, StatTile, RingMeter, RankedBars, DailyItemsChart, ItemFeed...)
├── lib/
│   ├── format.ts         # Source names, dates, numbers, safe links
│   ├── runs.ts           # Plain-language run status
│   └── chartColors.ts    # Validated chart colours per source type
├── pages/DashboardPage.tsx
└── test/                 # Test setup and a fake API (mockApi.ts)
```

Server data is fetched and cached with TanStack Query. Query keys: `health`, `item-stats`, `items`, `exploited` and `latest-run`.

## Design rules

- **Theme tokens** live in `src/index.css` (`hud-bg`, `hud-panel`, `hud-cyan`, `hud-magenta`...), plus status colours (`hud-ok`, `hud-warn`, `hud-danger`). Shared styles: `.hud-panel` (frame with glowing corner brackets), `.hud-heading` (title with the striped accent), `.hud-button` (clipped corners) and `.hud-chip`.
- **Chart colours** (`lib/chartColors.ts`) are fixed per source type: web is cyan `#1299b4`, advisory is magenta `#e8457a`, social is amber `#bf7f1a`. They were validated against the panel colour for lightness, colour-blind separation and contrast. A colour always follows the source type; it never changes by rank or filter. Text never uses these colours.
- **Severity and status** are always shown as an icon plus a word, never colour alone.
- **Links from collected data** go through `safeExternalUrl`, so only `http(s)` links are rendered. They open in a new tab with `rel="noopener noreferrer"`.
- **Accessibility:** semantic sections with headings, keyboard focus outlines, `aria-live` for run status, and a table view for the chart.

## Tests

`npm test` runs Vitest with Testing Library in jsdom. API calls go through a fake `fetch` (`src/test/mockApi.ts`), and the ECharts chart is stubbed.

| Test file | Covers |
|---|---|
| `pages/DashboardPage.test.tsx` | API online/unreachable, empty states, API error messages, data rendering, starting a run, cool-down message |
| `api/client.test.ts` | Query parameters, error envelope to `ApiError`, `Retry-After`, network failures, "no runs yet" |
| `lib/format.test.ts` | Safe links, source names, affected products, dates, numbers |
| `lib/runs.test.ts` | Run status descriptions |
