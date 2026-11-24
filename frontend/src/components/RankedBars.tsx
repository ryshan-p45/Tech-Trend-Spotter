import type { NamedCount } from '../api/types.ts'

type RankedBarsProps = {
  rows: NamedCount[]
  color: string
  emptyMessage: string
  ariaLabel: string
}

// Leaves 3rem beside the longest bar so its value label always fits at the tip
const barWidth = (count: number, max: number) => `max(4px, calc((100% - 3rem) * ${count / max}))`

// Horizontal bars for one series (one colour for every bar), value printed at the tip.
// Rendered as a list, so screen readers get every name and value without a separate table.
function RankedBars({ rows, color, emptyMessage, ariaLabel }: RankedBarsProps) {
  if (rows.length === 0) {
    return <p className="py-4 text-sm text-hud-muted">{emptyMessage}</p>
  }
  const max = Math.max(...rows.map((row) => row.count), 1)
  return (
    <ul aria-label={ariaLabel} className="flex flex-col gap-2.5">
      {rows.map((row) => (
        <li key={row.name} className="grid grid-cols-[minmax(0,9rem)_1fr] items-center gap-3 text-sm"
          title={`${row.name}: ${row.count}`}>
          <span className="truncate text-hud-text">{row.name}</span>
          <span className="flex items-center gap-2">
            <span className="h-2.5 rounded-r-[4px]" style={{ width: barWidth(row.count, max), backgroundColor: color }} />
            <span className="text-xs text-hud-muted tabular-nums">{row.count}</span>
          </span>
        </li>
      ))}
    </ul>
  )
}

export default RankedBars
