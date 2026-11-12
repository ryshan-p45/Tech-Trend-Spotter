import { useQuery } from '@tanstack/react-query'
import { getHealth } from '../api/client.ts'

// Placeholder dashboard - shows whether the backend API can be reached
function DashboardPage() {
  const health = useQuery({ queryKey: ['health'], queryFn: getHealth })

  return (
    <main className="min-h-svh p-8">
      <h1 className="text-2xl tracking-widest text-hud-cyan uppercase">Tech Trend Spotter</h1>

      <p className="mt-4 text-hud-muted">
        {health.isPending && 'Connecting to the API…'}
        {health.isError && 'Could not reach the API. Check that the backend is running.'}
        {health.isSuccess && 'API online'}
      </p>
    </main>
  )
}

export default DashboardPage
