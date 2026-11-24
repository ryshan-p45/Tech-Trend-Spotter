import type { Item, Severity } from '../api/types.ts'
import { SOURCE_TYPE_COLORS } from '../lib/chartColors.ts'
import { SOURCE_TYPE_LABELS, affectedSummary, relativeTime, safeExternalUrl, shortDate, sourceLabel } from '../lib/format.ts'

// Severity is a status: always shown as icon + word, never colour alone
const SEVERITY_STYLES: Record<Severity, { icon: string; className: string }> = {
  critical: { icon: '▲', className: 'text-hud-danger border-hud-danger/60' },
  high: { icon: '▲', className: 'text-hud-warn border-hud-warn/60' },
  medium: { icon: '◆', className: 'text-hud-text border-hud-border' },
  low: { icon: '▼', className: 'text-hud-muted border-hud-border' },
}

type ItemCardProps = { item: Item }

// One collected item: what it is, where it's from, and the details that matter for its type
function ItemCard({ item }: ItemCardProps) {
  const url = safeExternalUrl(item.url)
  const discussionUrl = safeExternalUrl(item.discussion_url)
  const affected = affectedSummary(item)

  return (
    <article className="border-l-2 py-1 pl-3" style={{ borderColor: SOURCE_TYPE_COLORS[item.source_type] }}>
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-hud-muted">
        <span className="tracking-wider uppercase">{SOURCE_TYPE_LABELS[item.source_type]}</span>
        <span aria-hidden="true">·</span>
        <span>{sourceLabel(item.source_name, item.site_name)}</span>
        <span aria-hidden="true">·</span>
        <time dateTime={item.published_at ?? item.first_collected_at}>
          {relativeTime(item.published_at ?? item.first_collected_at)}
        </time>
      </p>

      <h3 className="mt-1 text-sm leading-snug font-semibold text-hud-text">
        {url ? (
          <a href={url} target="_blank" rel="noopener noreferrer" className="hover:text-hud-cyan hover:underline">
            {item.title}
            <span className="sr-only"> (opens in a new tab)</span>
          </a>
        ) : item.title}
      </h3>

      {item.source_type === 'advisory' && <AdvisoryDetails item={item} affected={affected} />}

      {item.summary && <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-hud-muted">{item.summary}</p>}

      {item.source_type === 'social' && (
        <p className="mt-1.5 flex flex-wrap gap-3 text-xs text-hud-muted">
          {item.score !== null && <span>{item.score} points</span>}
          {item.comment_count !== null && (
            discussionUrl ? (
              <a href={discussionUrl} target="_blank" rel="noopener noreferrer" className="hover:text-hud-cyan hover:underline">
                {item.comment_count} comments<span className="sr-only"> (opens in a new tab)</span>
              </a>
            ) : <span>{item.comment_count} comments</span>
          )}
        </p>
      )}
    </article>
  )
}

// CVE, severity, exploitation flags and affected products for advisories
function AdvisoryDetails({ item, affected }: { item: Item; affected: string | null }) {
  const severity = item.severity ? SEVERITY_STYLES[item.severity] : null
  return (
    <div className="mt-1.5 flex flex-col gap-1.5">
      <div className="flex flex-wrap gap-1.5">
        {item.cve_id && <span className="hud-chip">{item.cve_id}</span>}
        {severity && item.severity && (
          <span className={`hud-chip ${severity.className}`}>
            <span aria-hidden="true">{severity.icon}</span>{item.severity}
          </span>
        )}
        {item.known_exploited && (
          <span className="hud-chip border-hud-danger/60 text-hud-danger">
            <span aria-hidden="true">⚠</span>Exploited in the wild
          </span>
        )}
        {item.known_ransomware_use && (
          <span className="hud-chip border-hud-danger/60 text-hud-danger">
            <span aria-hidden="true">⚠</span>Ransomware
          </span>
        )}
      </div>
      {affected && <p className="text-xs text-hud-text"><span className="text-hud-muted">Affects </span>{affected}</p>}
      {item.remediation_due_date && (
        <p className="text-xs text-hud-muted">Fix due {shortDate(item.remediation_due_date)}</p>
      )}
    </div>
  )
}

export default ItemCard
