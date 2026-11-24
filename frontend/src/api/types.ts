/*
 * TypeScript mirror of the backend API contract (backend/interfaces/api_interfaces.py).
 * Keep the two in sync: a field added there should be added here.
 */

export type SourceType = 'web' | 'social' | 'advisory'
export type Severity = 'low' | 'medium' | 'high' | 'critical'
export type RunStatus = 'queued' | 'running' | 'completed' | 'failed'

// ---------- Envelopes ----------

export type DataResponse<T> = { data: T }

export type PageResponse<T> = {
  data: T[]
  pagination: { next_cursor: string | null; limit: number }
}

export type ErrorResponse = { error: { code: string; message: string } }

// ---------- Resources ----------

export type HealthStatus = { status: 'ok' }

export type AffectedProduct = {
  vendor: string | null
  product: string
  ecosystem: string | null
}

// One collected item. Fields that don't apply to its source type are null.
export type Item = {
  item_id: string
  source_type: SourceType
  source_name: string
  title: string
  url: string | null
  summary: string | null
  tags: string[]
  published_at: string | null
  first_collected_at: string
  site_name: string | null
  score: number | null
  comment_count: number | null
  discussion_url: string | null
  cve_id: string | null
  affected: AffectedProduct[] | null
  severity: Severity | null
  known_exploited: boolean | null
  known_ransomware_use: boolean | null
  remediation_due_date: string | null
}

export type NamedCount = { name: string; count: number }

export type DailyCount = { date: string; web: number; social: number; advisory: number }

export type ItemStats = {
  days: number
  total_items: number
  by_source_type: Record<SourceType, number>
  by_source: { source_name: string; source_type: SourceType; count: number }[]
  daily_counts: DailyCount[]
  advisory_severity: Record<Severity | 'unrated', number>
  known_exploited: number
  top_vendors: NamedCount[]
  top_ecosystems: NamedCount[]
}

export type RunSourceResult = {
  source_name: string
  source_type: SourceType
  status: 'success' | 'failed'
  items: number
  skipped: number
  error_message: string | null
}

export type CollectionRun = {
  run_id: string
  status: RunStatus
  requested_at: string
  started_at: string | null
  finished_at: string | null
  items_collected: number
  items_new: number
  sources: RunSourceResult[]
  error_message: string | null
}
