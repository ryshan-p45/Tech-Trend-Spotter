import { useQuery } from '@tanstack/react-query'
import { getLatestRun } from '../api/client.ts'
import { SOURCE_TYPE_COLORS } from '../lib/chartColors.ts'
import { sourceLabel } from '../lib/format.ts'
import { isRunActive } from '../lib/runs.ts'
import Panel from './Panel.tsx'
import StateMessage from './StateMessage.tsx'

// Outcome of each source in the latest finished run: whether it worked and how many items it gave
function SourceStatus() {
  // Same query as the run control, so it shares the cache and the polling
  const latestRun = useQuery({ queryKey: ['latest-run'], queryFn: getLatestRun })
  const run = latestRun.data ?? null

  return (
    <Panel title="Sources" subtitle="Result of the latest collection run">
      {latestRun.isPending && <StateMessage kind="loading" message="Loading source status…" />}
      {latestRun.isError && <StateMessage kind="error" message={latestRun.error.message} />}
      {latestRun.isSuccess && !run && (
        <StateMessage kind="empty" message='No runs yet. Press "Run collection" to check every source.' />
      )}
      {run && isRunActive(run) && <StateMessage kind="loading" message="A run is in progress. Results appear here when it finishes." />}
      {run && !isRunActive(run) && run.sources.length === 0 && (
        <StateMessage kind="error" message={run.error_message ?? 'The last run did not reach any sources. Start a new run.'} />
      )}
      {run && !isRunActive(run) && run.sources.length > 0 && (
        <ul className="flex flex-col gap-2 text-sm">
          {run.sources.map((source) => (
            <li key={source.source_name} className="flex flex-col gap-1">
              <div className="flex items-center justify-between gap-3">
                <span className="flex min-w-0 items-center gap-2">
                  <span aria-hidden="true" className="h-2 w-2 shrink-0 rounded-full"
                    style={{ backgroundColor: SOURCE_TYPE_COLORS[source.source_type] }} />
                  <span className="truncate">{sourceLabel(source.source_name)}</span>
                </span>
                {source.status === 'success' ? (
                  <span className="shrink-0 text-xs text-hud-ok"><span aria-hidden="true">✓ </span>{source.items} items</span>
                ) : (
                  <span className="shrink-0 text-xs text-hud-danger"><span aria-hidden="true">✕ </span>Failed</span>
                )}
              </div>
              {source.status === 'failed' && (
                <details className="pl-4 text-xs text-hud-muted">
                  <summary className="cursor-pointer hover:text-hud-text">Why?</summary>
                  <p className="mt-1 break-words">{source.error_message ?? 'No reason was given.'} It will be retried on the next run.</p>
                </details>
              )}
            </li>
          ))}
        </ul>
      )}
    </Panel>
  )
}

export default SourceStatus
