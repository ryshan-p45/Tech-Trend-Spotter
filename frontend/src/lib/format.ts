import type { Item, SourceType } from '../api/types.ts'

/*
 * Formatting helpers that turn API values into plain-language text for the UI.
 * Pure functions, so they are easy to test and reuse.
 */

// Readable names for the source identifiers the backend uses
const SOURCE_LABELS: Record<string, string> = {
  hacker_news: 'Hacker News',
  cisa_kev: 'CISA KEV',
  github_advisories: 'GitHub Advisories',
}

export const SOURCE_TYPE_LABELS: Record<SourceType, string> = {
  web: 'News',
  social: 'Discussions',
  advisory: 'Advisories',
}

// "rss:krebsonsecurity" -> "krebsonsecurity"; known sources get their proper name
export function sourceLabel(sourceName: string, siteName?: string | null): string {
  if (siteName) return siteName
  if (SOURCE_LABELS[sourceName]) return SOURCE_LABELS[sourceName]
  return sourceName.startsWith('rss:') ? sourceName.slice(4) : sourceName
}

// 1234 -> "1,234", 12900 -> "12.9K"
export function compactNumber(value: number): string {
  return new Intl.NumberFormat('en', { notation: value >= 10_000 ? 'compact' : 'standard', maximumFractionDigits: 1 })
    .format(value)
}

// "3 hours ago", "2 days ago"; falls back to a date for anything older than 30 days
export function relativeTime(isoDate: string | null, now: Date = new Date()): string {
  if (!isoDate) return 'Date unknown'
  const then = new Date(isoDate)
  const seconds = Math.round((now.getTime() - then.getTime()) / 1000)
  if (seconds < 60) return 'just now'
  const units: [Intl.RelativeTimeFormatUnit, number][] = [['minute', 60], ['hour', 3600], ['day', 86400]]
  const formatter = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })
  if (seconds < 3600) return formatter.format(-Math.floor(seconds / units[0][1]), 'minute')
  if (seconds < 86400) return formatter.format(-Math.floor(seconds / units[1][1]), 'hour')
  if (seconds < 30 * 86400) return formatter.format(-Math.floor(seconds / units[2][1]), 'day')
  return shortDate(isoDate)
}

// "2026-11-24" or an ISO datetime -> "24 Nov 2026" (UTC, so a date-only value never shifts a day)
export function shortDate(isoDate: string): string {
  return new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' })
    .format(new Date(isoDate))
}

// Only http(s) links from collected data are rendered - never javascript: or data: URLs
export function safeExternalUrl(url: string | null): string | null {
  if (!url) return null
  try {
    const parsed = new URL(url)
    return parsed.protocol === 'https:' || parsed.protocol === 'http:' ? parsed.toString() : null
  } catch {
    return null
  }
}

// "Acme Widget", "wwbn/avideo (composer)"; lists the first few and counts the rest
export function affectedSummary(item: Item, max = 3): string | null {
  const affected = item.affected ?? []
  if (affected.length === 0) return null
  const names = affected.slice(0, max).map((product) => {
    const name = product.vendor ? `${product.vendor} ${product.product}` : product.product
    return product.ecosystem ? `${name} (${product.ecosystem})` : name
  })
  const extra = affected.length - max
  return extra > 0 ? `${names.join(', ')} +${extra} more` : names.join(', ')
}
