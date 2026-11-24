type RingMeterProps = {
  label: string
  value: number
  total: number
  caption: string
}

const RADIUS = 42
const CIRCUMFERENCE = 2 * Math.PI * RADIUS

// Circular meter for one share of a whole (e.g. exploited advisories out of all advisories).
// The track is a lighter step of the same hue, so the whole ring reads as one scale.
function RingMeter({ label, value, total, caption }: RingMeterProps) {
  const share = total > 0 ? value / total : 0
  const percent = Math.round(share * 100)
  return (
    <figure className="flex items-center gap-4">
      <svg viewBox="0 0 100 100" className="h-28 w-28 shrink-0 -rotate-90" role="img"
        aria-label={`${label}: ${value} of ${total} (${percent}%)`}>
        <circle cx="50" cy="50" r={RADIUS} fill="none" stroke="rgb(232 69 122 / 0.18)" strokeWidth="8" />
        <circle cx="50" cy="50" r={RADIUS} fill="none" stroke="#e8457a" strokeWidth="8" strokeLinecap="round"
          strokeDasharray={`${share * CIRCUMFERENCE} ${CIRCUMFERENCE}`}
          style={{ filter: 'drop-shadow(0 0 4px rgb(232 69 122 / 0.6))' }} />
      </svg>
      <figcaption>
        <p className="text-3xl font-semibold text-hud-text">{percent}%</p>
        <p className="text-sm text-hud-text">{label}</p>
        <p className="text-xs text-hud-muted">{caption}</p>
      </figcaption>
    </figure>
  )
}

export default RingMeter
