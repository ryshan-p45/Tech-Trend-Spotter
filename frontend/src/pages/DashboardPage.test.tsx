import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import DashboardPage from './DashboardPage.tsx'
import { emptyStats, mockApi, page, sampleItem, sampleRun, type Routes } from '../test/mockApi.ts'

// ECharts needs a real canvas/layout; the chart is replaced with a stub that shows it was rendered
vi.mock('echarts-for-react/lib/core', () => ({
  default: (props: { 'aria-label'?: string }) => <div role="img" aria-label={props['aria-label']} />,
}))

// Renders the page with a fresh query cache (retries off so errors show immediately)
function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  render(<DashboardPage />, { wrapper })
}

const noRunsYet = { status: 404, body: { error: { code: 'no_runs', message: 'No collection has been run yet.' } } }

const emptyDatabase: Routes = {
  'GET /health': { body: { data: { status: 'ok' } } },
  'GET /item-stats': { body: { data: emptyStats() } },
  'GET /items': { body: page([]) },
  'GET /collection-runs/latest': noRunsYet,
}

describe('DashboardPage', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('shows the API as online when the health check succeeds', async () => {
    mockApi(emptyDatabase)
    renderPage()
    expect(await screen.findByText('API online')).toBeInTheDocument()
  })

  it('tells the user what to do when the API is unreachable', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    renderPage()
    expect(await screen.findByText(/Could not reach the API\. Check that the backend is running/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Run collection/ })).not.toBeInTheDocument()
  })

  it('explains how to get data when nothing has been collected', async () => {
    mockApi(emptyDatabase)
    renderPage()
    expect(await screen.findByText(/Nothing collected yet/)).toBeInTheDocument()
    expect(screen.getByText('No collection has run yet.')).toBeInTheDocument()
    expect(screen.getByText(/No data yet/)).toBeInTheDocument()
  })

  it('shows the database error message from the API', async () => {
    mockApi({
      ...emptyDatabase,
      'GET /item-stats': { status: 503, body: { error: { code: 'database_unavailable', message: "The database can't be reached right now." } } },
    })
    renderPage()
    expect(await screen.findByText("The database can't be reached right now.")).toBeInTheDocument()
  })

  it('shows figures, the chart, items and source results when data exists', async () => {
    mockApi({
      ...emptyDatabase,
      'GET /item-stats': { body: { data: emptyStats({
        total_items: 121,
        by_source: [{ source_name: 'cisa_kev', source_type: 'advisory', count: 36 }],
        daily_counts: [{ date: '2026-11-24', web: 3, social: 5, advisory: 2 }],
        advisory_severity: { critical: 2, high: 3, medium: 1, low: 0, unrated: 4 },
        known_exploited: 4,
        top_vendors: [{ name: 'Acme', count: 3 }],
      }) } },
      'GET /items': { body: page([sampleItem()]) },
      'GET /collection-runs/latest': { body: { data: sampleRun() } },
    })
    renderPage()

    expect(await screen.findByText('121')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /Items collected per day/ })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Exploited in the wild: 4 of 10 (40%)' })).toBeInTheDocument()
    expect(within(screen.getByRole('list', { name: 'Most affected vendors' })).getByText('Acme')).toBeInTheDocument()
    expect((await screen.findAllByText('Acme Widget')).length).toBeGreaterThan(0)
    expect(screen.getByText(/121 items \(8 new\)\. 1 of 2 sources failed/)).toBeInTheDocument()
    expect(screen.getByText('Failed')).toBeInTheDocument()
  })

  it('starts a collection run and shows that it is collecting', async () => {
    let latest: object = noRunsYet
    mockApi({
      ...emptyDatabase,
      'GET /collection-runs/latest': () => latest as never,
      'POST /collection-runs': () => {
        latest = { body: { data: sampleRun({ status: 'running', finished_at: null, sources: [] }) } }
        return { status: 202, body: { data: sampleRun({ status: 'queued', finished_at: null, sources: [] }) } }
      },
    })
    renderPage()

    fireEvent.click(await screen.findByRole('button', { name: /Run collection/ }))

    expect(await screen.findByRole('button', { name: /Collecting/ })).toBeDisabled()
  })

  it('tells the user how long to wait when runs are on cool-down', async () => {
    mockApi({
      ...emptyDatabase,
      'POST /collection-runs': { status: 429, headers: { 'Retry-After': '120' },
        body: { error: { code: 'run_cooldown', message: 'A run was started recently. Try again in 120 seconds.' } } },
    })
    renderPage()

    fireEvent.click(await screen.findByRole('button', { name: /Run collection/ }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Try again in 120 seconds')
  })
})
