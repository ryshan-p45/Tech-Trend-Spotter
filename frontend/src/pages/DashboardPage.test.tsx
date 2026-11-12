import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import DashboardPage from './DashboardPage.tsx'

// Renders the page with a fresh query cache (retries off so errors show immediately)
function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <DashboardPage />
    </QueryClientProvider>,
  )
}

describe('DashboardPage', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('shows the API as online when the health check succeeds', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: 'ok' }))))
    renderPage()
    expect(await screen.findByText('API online')).toBeInTheDocument()
  })

  it('tells the user what to do when the API is unreachable', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 500 })))
    renderPage()
    expect(await screen.findByText(/Could not reach the API/)).toBeInTheDocument()
  })
})
