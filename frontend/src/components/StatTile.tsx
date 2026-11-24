type StatTileProps = {
  label: string
  value: string
  hint?: string
  hero?: boolean
}

// A single headline number. `hero` makes it the one large figure the dashboard leads with.
function StatTile({ label, value, hint, hero = false }: StatTileProps) {
  return (
    <div className="hud-panel flex flex-col justify-between gap-2">
      <p className="text-xs tracking-wider text-hud-muted">{label}</p>
      <p className={`font-semibold text-hud-text ${hero ? 'text-5xl' : 'text-3xl'}`}>{value}</p>
      {hint && <p className="text-xs text-hud-muted">{hint}</p>}
    </div>
  )
}

export default StatTile
