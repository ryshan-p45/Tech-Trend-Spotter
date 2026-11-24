import type { CollectionRun } from '../api/types.ts'
import { relativeTime } from './format.ts'

/*
 * Plain-language descriptions of a collection run, shared by the run control and the source panel.
 */

export const isRunActive = (run: CollectionRun | null | undefined): boolean =>
  run?.status === 'queued' || run?.status === 'running'

// One sentence describing the latest run, e.g. "Last run 5 minutes ago: 121 items (8 new). 1 of 6 sources failed."
export function describeRun(run: CollectionRun | null, now: Date = new Date()): string {
  if (!run) return 'No collection has run yet.'
  if (run.status === 'queued') return 'Collection queued…'
  if (run.status === 'running') return 'Collecting from all sources… this usually takes under a minute.'
  if (run.status === 'failed') return `Last run failed. ${run.error_message ?? 'Start a new run to try again.'}`

  const when = relativeTime(run.finished_at ?? run.requested_at, now)
  const failed = run.sources.filter((source) => source.status === 'failed').length
  const sourcesNote = failed > 0 ? ` ${failed} of ${run.sources.length} sources failed - see Sources.` : ''
  return `Last run ${when}: ${run.items_collected} items (${run.items_new} new).${sourcesNote}`
}
