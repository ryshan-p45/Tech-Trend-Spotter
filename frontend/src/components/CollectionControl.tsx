import { useEffect, useRef } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, getLatestRun, startRun } from '../api/client.ts'
import { describeRun, isRunActive } from '../lib/runs.ts'

// How often to check on a run while it's queued or running
const POLL_INTERVAL_MS = 2000

/*
 * "Run collection" button plus a live status line.
 *
 * Flow: POST starts a run (202) -> the latest-run query polls every 2s while it is
 * active -> when it finishes, items and stats are refreshed so the new data appears.
 * 409 (already running) just resumes following the active run; 429 (cool-down)
 * tells the user how long to wait.
 */
function CollectionControl() {
  const queryClient = useQueryClient()

  const latestRun = useQuery({
    queryKey: ['latest-run'],
    queryFn: getLatestRun,
    refetchInterval: (query) => (isRunActive(query.state.data) ? POLL_INTERVAL_MS : false),
  })

  const start = useMutation({
    mutationFn: startRun,
    onSuccess: (run) => queryClient.setQueryData(['latest-run'], run),
    onError: (error) => {
      // Someone else started a run: follow that one instead
      if (error instanceof ApiError && error.code === 'run_in_progress') {
        void queryClient.invalidateQueries({ queryKey: ['latest-run'] })
      }
    },
  })

  useRefreshDataWhenRunFinishes(latestRun.data?.status)

  const run = latestRun.data ?? null
  const active = isRunActive(run)
  const startError = start.isError && !(start.error instanceof ApiError && start.error.code === 'run_in_progress')
    ? start.error.message
    : null

  return (
    <div className="flex flex-col items-start gap-2 sm:items-end">
      <button type="button" className="hud-button" onClick={() => start.mutate()} disabled={active || start.isPending}>
        <span aria-hidden="true" className={active ? 'animate-spin' : ''}>{active ? '◌' : '▶'}</span>
        {active ? 'Collecting…' : 'Run collection'}
      </button>
      <p aria-live="polite" className="max-w-md text-xs text-hud-muted sm:text-right">
        {latestRun.isPending && 'Checking the last collection run…'}
        {latestRun.isError && latestRun.error.message}
        {latestRun.isSuccess && describeRun(run)}
      </p>
      {startError && <p role="alert" className="max-w-md text-xs text-hud-danger sm:text-right">{startError}</p>}
    </div>
  )
}

// When a run goes from active to finished, refetch everything that shows collected data
function useRefreshDataWhenRunFinishes(status: string | undefined) {
  const queryClient = useQueryClient()
  const previousStatus = useRef(status)

  useEffect(() => {
    const wasActive = previousStatus.current === 'queued' || previousStatus.current === 'running'
    const isFinished = status === 'completed' || status === 'failed'
    if (wasActive && isFinished) {
      void queryClient.invalidateQueries({ queryKey: ['items'] })
      void queryClient.invalidateQueries({ queryKey: ['item-stats'] })
      void queryClient.invalidateQueries({ queryKey: ['exploited'] })
    }
    previousStatus.current = status
  }, [status, queryClient])
}

export default CollectionControl
