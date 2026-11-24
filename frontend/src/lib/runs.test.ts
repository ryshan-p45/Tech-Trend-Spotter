import { describe, expect, it } from 'vitest'
import { describeRun, isRunActive } from './runs.ts'
import { sampleRun } from '../test/mockApi.ts'

describe('run descriptions', () => {
  it('describes each run state in plain language', () => {
    expect(describeRun(null)).toBe('No collection has run yet.')
    expect(describeRun(sampleRun({ status: 'running' }))).toMatch(/Collecting from all sources/)
    expect(describeRun(sampleRun({ status: 'failed', error_message: 'The server restarted.' })))
      .toBe('Last run failed. The server restarted.')
    expect(describeRun(sampleRun())).toMatch(/121 items \(8 new\)\. 1 of 2 sources failed/)
  })

  it('knows when a run is still active', () => {
    expect(isRunActive(sampleRun({ status: 'queued' }))).toBe(true)
    expect(isRunActive(sampleRun({ status: 'completed' }))).toBe(false)
    expect(isRunActive(null)).toBe(false)
  })
})
