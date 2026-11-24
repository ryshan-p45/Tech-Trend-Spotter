import { vi } from 'vitest'
import type { CollectionRun, Item, ItemStats } from '../api/types.ts'

/*
 * Test helpers: a fake fetch that answers by URL path, and sample API data.
 * Lets component tests run the real API client without a backend.
 */

type Route = { status?: number; body: unknown; headers?: Record<string, string> }
export type Routes = Record<string, Route | (() => Route)>

// Stubs global fetch. Keys are "METHOD /path" (query string ignored), e.g. "GET /items"
export function mockApi(routes: Routes) {
  const fetchMock = vi.fn(async (input: string | URL, init?: RequestInit) => {
    const url = new URL(String(input))
    const key = `${init?.method ?? 'GET'} ${url.pathname.replace(/^\/v1/, '')}`
    const entry = routes[key]
    if (!entry) return new Response(JSON.stringify({ error: { code: 'not_found', message: 'Not mocked' } }), { status: 404 })
    const route = typeof entry === 'function' ? entry() : entry
    return new Response(JSON.stringify(route.body), { status: route.status ?? 200, headers: route.headers })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

export const sampleItem = (overrides: Partial<Item> = {}): Item => ({
  item_id: 'a'.repeat(64),
  source_type: 'advisory',
  source_name: 'cisa_kev',
  title: 'Acme Widget Path Traversal Vulnerability',
  url: 'https://nvd.nist.gov/vuln/detail/CVE-2026-1234',
  summary: 'Lets an attacker write files.',
  tags: ['CWE-24'],
  published_at: '2026-11-23T00:00:00Z',
  first_collected_at: '2026-11-24T05:00:00Z',
  site_name: null,
  score: null,
  comment_count: null,
  discussion_url: null,
  cve_id: 'CVE-2026-1234',
  affected: [{ vendor: 'Acme', product: 'Widget', ecosystem: null }],
  severity: null,
  known_exploited: true,
  known_ransomware_use: false,
  remediation_due_date: '2026-12-14',
  ...overrides,
})

export const emptyStats = (overrides: Partial<ItemStats> = {}): ItemStats => ({
  days: 14,
  total_items: 0,
  by_source_type: { web: 0, social: 0, advisory: 0 },
  by_source: [],
  daily_counts: [],
  advisory_severity: { critical: 0, high: 0, medium: 0, low: 0, unrated: 0 },
  known_exploited: 0,
  top_vendors: [],
  top_ecosystems: [],
  ...overrides,
})

export const sampleRun = (overrides: Partial<CollectionRun> = {}): CollectionRun => ({
  run_id: '11111111-1111-1111-1111-111111111111',
  status: 'completed',
  requested_at: new Date(Date.now() - 5 * 60_000).toISOString(),
  started_at: new Date(Date.now() - 5 * 60_000).toISOString(),
  finished_at: new Date(Date.now() - 4 * 60_000).toISOString(),
  items_collected: 121,
  items_new: 8,
  sources: [
    { source_name: 'cisa_kev', source_type: 'advisory', status: 'success', items: 36, skipped: 0, error_message: null },
    { source_name: 'github_advisories', source_type: 'advisory', status: 'failed', items: 0, skipped: 0,
      error_message: 'https://api.github.com/advisories returned status 403' },
  ],
  error_message: null,
  ...overrides,
})

export const page = (data: Item[], nextCursor: string | null = null) =>
  ({ data, pagination: { next_cursor: nextCursor, limit: 20 } })
