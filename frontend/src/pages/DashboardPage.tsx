import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getHealth, getItemStats } from '../api/client.ts'
import type { ItemStats } from '../api/types.ts'
import CollectionControl from '../components/CollectionControl.tsx'
import DailyItemsChart from '../components/DailyItemsChart.tsx'
import ExploitedList from '../components/ExploitedList.tsx'
import ItemFeed from '../components/ItemFeed.tsx'
import Panel from '../components/Panel.tsx'
import RankedBars from '../components/RankedBars.tsx'
import RingMeter from '../components/RingMeter.tsx'
import SourceStatus from '../components/SourceStatus.tsx'
import StatTile from '../components/StatTile.tsx'
import StateMessage from '../components/StateMessage.tsx'
import { SOURCE_TYPE_COLORS } from '../lib/chartColors.ts'
import { compactNumber } from '../lib/format.ts'

// Days covered by the chart and the advisory figures
const STATS_WINDOW_DAYS = 14

/*
 * Main dashboard: what has been collected, what's exploited, who's affected, and the feed.
 *
 * Layout (top to bottom):
 *   header      - title, API status, Run collection
 *   stat tiles  - headline numbers
 *   activity    - items per day (chart) | exposure (exploited share + severity)
 *   detail      - latest signals feed  | exploited list, top vendors/ecosystems, sources
 */
function DashboardPage() {
  const health = useQuery({ queryKey: ['health'], queryFn: getHealth })

  return (
    <div className="mx-auto flex min-h-svh max-w-7xl flex-col gap-5 p-4 sm:p-6 lg:p-8">
      <header className="flex flex-col justify-between gap-4 border-b border-hud-border/60 pb-5 sm:flex-row sm:items-end">
        <div>
          <p className="text-[11px] tracking-[0.3em] text-hud-magenta uppercase">Signal intelligence</p>
          <h1 className="mt-1 text-2xl font-bold tracking-[0.2em] text-hud-cyan uppercase sm:text-3xl"
            style={{ textShadow: '0 0 12px rgb(63 216 242 / 0.45)' }}>
            Tech Trend Spotter
          </h1>
          <p className="mt-2 flex items-center gap-2 text-xs text-hud-muted" aria-live="polite">
            <span aria-hidden="true" className={`h-2 w-2 rounded-full ${
              health.isSuccess ? 'bg-hud-ok' : health.isError ? 'bg-hud-danger' : 'bg-hud-muted'}`} />
            {health.isPending && 'Connecting to the API…'}
            {health.isError && 'Could not reach the API. Check that the backend is running.'}
            {health.isSuccess && 'API online'}
          </p>
        </div>
        {health.isSuccess && <CollectionControl />}
      </header>

      <main className="flex flex-col gap-5">
        {health.isPending && <StateMessage kind="loading" message="Connecting to the API…" />}
        {health.isError && <ApiUnreachable />}
        {health.isSuccess && <Dashboard />}
      </main>
    </div>
  )
}

// Shown instead of the panels when the API can't be reached, so the same error isn't repeated in every panel
function ApiUnreachable() {
  const queryClient = useQueryClient()
  return (
    <div className="hud-panel flex flex-col items-start gap-4">
      <p className="text-sm text-hud-text">
        The dashboard needs the backend API, which isn't responding. Start it with{' '}
        <code className="text-hud-cyan">uvicorn main:app --reload</code> in the backend folder, then try again.
      </p>
      <button type="button" className="hud-button" onClick={() => void queryClient.invalidateQueries()}>
        Try again
      </button>
    </div>
  )
}

// All data panels; only rendered once the API is reachable
function Dashboard() {
  const stats = useQuery({ queryKey: ['item-stats', STATS_WINDOW_DAYS], queryFn: () => getItemStats(STATS_WINDOW_DAYS) })
  return (
    <>
      {stats.isPending && <StateMessage kind="loading" message="Loading the latest figures…" />}
      {stats.isError && <StateMessage kind="error" message={stats.error.message} />}
      {stats.isSuccess && <Overview stats={stats.data} />}

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="lg:col-span-2"><ItemFeed /></div>
        <div className="flex flex-col gap-5">
          <ExploitedList />
          <SourceStatus />
        </div>
      </div>
    </>
  )
}

// Stat tiles, activity chart and exposure panels - everything driven by /item-stats
function Overview({ stats }: { stats: ItemStats }) {
  const severity = stats.advisory_severity
  const advisoriesInWindow = severity.critical + severity.high + severity.medium + severity.low + severity.unrated
  const severityRows = [
    { name: 'Critical', count: severity.critical },
    { name: 'High', count: severity.high },
    { name: 'Medium', count: severity.medium },
    { name: 'Low', count: severity.low },
    { name: 'Not rated', count: severity.unrated },
  ]
  const windowLabel = `last ${stats.days} days`

  return (
    <>
      <section aria-label="Headline figures" className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile hero label="Items collected" value={compactNumber(stats.total_items)}
          hint={`From ${stats.by_source.length} sources`} />
        <StatTile label="Advisories" value={compactNumber(advisoriesInWindow)} hint={`Published in the ${windowLabel}`} />
        <StatTile label="Exploited in the wild" value={compactNumber(stats.known_exploited)} hint={`Confirmed, ${windowLabel}`} />
        <StatTile label="Critical or high" value={compactNumber(severity.critical + severity.high)}
          hint={`Advisories, ${windowLabel}`} />
      </section>

      <div className="grid gap-5 lg:grid-cols-3">
        <Panel title="Activity" subtitle={`Items per day, ${windowLabel}`} className="lg:col-span-2">
          {stats.total_items === 0
            ? <StateMessage kind="empty" message='No data yet. Press "Run collection" to start collecting.' />
            : <DailyItemsChart days={stats.daily_counts} />}
        </Panel>

        <Panel title="Exposure" subtitle={`Advisories, ${windowLabel}`}>
          {advisoriesInWindow === 0 ? (
            <StateMessage kind="empty" message="No advisories in this period yet. They appear after the next run." />
          ) : (
            <div className="flex flex-col gap-6">
              <RingMeter label="Exploited in the wild" value={stats.known_exploited} total={advisoriesInWindow}
                caption={`${stats.known_exploited} of ${advisoriesInWindow} advisories`} />
              <RankedBars rows={severityRows} color={SOURCE_TYPE_COLORS.advisory} ariaLabel="Advisories by severity"
                emptyMessage="No severity data yet." />
            </div>
          )}
        </Panel>
      </div>

      <div className="grid gap-5 md:grid-cols-2">
        <Panel title="Most affected vendors" subtitle={`Named in advisories, ${windowLabel}`}>
          <RankedBars rows={stats.top_vendors} color={SOURCE_TYPE_COLORS.advisory} ariaLabel="Most affected vendors"
            emptyMessage="No vendors named in advisories yet." />
        </Panel>
        <Panel title="Most affected ecosystems" subtitle={`Package ecosystems in advisories, ${windowLabel}`}>
          <RankedBars rows={stats.top_ecosystems} color={SOURCE_TYPE_COLORS.advisory} ariaLabel="Most affected package ecosystems"
            emptyMessage="No package ecosystems in advisories yet." />
        </Panel>
      </div>
    </>
  )
}

export default DashboardPage
