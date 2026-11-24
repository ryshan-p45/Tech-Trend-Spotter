import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, getLatestRun, listItems, startRun } from './client.ts'
import { mockApi, page } from '../test/mockApi.ts'

describe('API client', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('sends filters as query parameters and leaves out empty ones', async () => {
    const fetchMock = mockApi({ 'GET /items': { body: page([]) } })
    await listItems({ sourceType: 'advisory', limit: 10, cursor: null })
    const url = new URL(String(fetchMock.mock.calls[0][0]))
    expect(url.searchParams.get('source_type')).toBe('advisory')
    expect(url.searchParams.get('limit')).toBe('10')
    expect(url.searchParams.has('cursor')).toBe(false)
  })

  it('turns the error envelope into an ApiError with the API message and Retry-After', async () => {
    mockApi({ 'POST /collection-runs': { status: 429, headers: { 'Retry-After': '30' },
      body: { error: { code: 'run_cooldown', message: 'Try again in 30 seconds.' } } } })
    const error = await startRun().catch((caught: unknown) => caught)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 429, code: 'run_cooldown', message: 'Try again in 30 seconds.', retryAfterSeconds: 30 })
  })

  it('gives a readable message when the backend cannot be reached', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    await expect(listItems({})).rejects.toMatchObject({ code: 'network_error' })
  })

  it('falls back to a generic message when the error body is not the envelope', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('<html>Bad gateway</html>', { status: 502 })))
    await expect(listItems({})).rejects.toMatchObject({ code: 'unknown_error', status: 502 })
  })

  it('returns null for the latest run when none has happened yet', async () => {
    mockApi({ 'GET /collection-runs/latest': { status: 404, body: { error: { code: 'no_runs', message: 'None' } } } })
    await expect(getLatestRun()).resolves.toBeNull()
  })
})
