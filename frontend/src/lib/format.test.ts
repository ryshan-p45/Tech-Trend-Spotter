import { describe, expect, it } from 'vitest'
import { affectedSummary, compactNumber, relativeTime, safeExternalUrl, shortDate, sourceLabel } from './format.ts'
import { sampleItem } from '../test/mockApi.ts'

describe('format helpers', () => {
  it('only allows http(s) links from collected data', () => {
    expect(safeExternalUrl('https://example.com/a')).toBe('https://example.com/a')
    expect(safeExternalUrl('javascript:alert(1)')).toBeNull()
    expect(safeExternalUrl('data:text/html,hi')).toBeNull()
    expect(safeExternalUrl('not a url')).toBeNull()
    expect(safeExternalUrl(null)).toBeNull()
  })

  it('names sources in plain language', () => {
    expect(sourceLabel('cisa_kev')).toBe('CISA KEV')
    expect(sourceLabel('rss:krebsonsecurity')).toBe('krebsonsecurity')
    expect(sourceLabel('rss:krebsonsecurity', 'Krebs on Security')).toBe('Krebs on Security')
  })

  it('summarises affected products and counts the rest', () => {
    const item = sampleItem({ affected: [
      { vendor: null, product: 'pkg-a', ecosystem: 'npm' },
      { vendor: 'Acme', product: 'Widget', ecosystem: null },
      { vendor: null, product: 'pkg-c', ecosystem: 'pip' },
      { vendor: null, product: 'pkg-d', ecosystem: 'pip' },
    ] })
    expect(affectedSummary(item)).toBe('pkg-a (npm), Acme Widget, pkg-c (pip) +1 more')
    expect(affectedSummary(sampleItem({ affected: [] }))).toBeNull()
  })

  it('formats relative times and dates', () => {
    const now = new Date('2026-11-24T12:00:00Z')
    expect(relativeTime('2026-11-24T11:59:30Z', now)).toBe('just now')
    expect(relativeTime('2026-11-24T09:00:00Z', now)).toBe('3 hours ago')
    expect(relativeTime('2026-11-21T12:00:00Z', now)).toBe('3 days ago')
    expect(relativeTime(null, now)).toBe('Date unknown')
    expect(shortDate('2026-12-14')).toBe('14 Dec 2026')
  })

  it('compacts large numbers only', () => {
    expect(compactNumber(1284)).toBe('1,284')
    expect(compactNumber(12_900)).toBe('12.9K')
  })
})
