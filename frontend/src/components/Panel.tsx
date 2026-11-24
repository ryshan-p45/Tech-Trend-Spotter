import { useId, type ReactNode } from 'react'

type PanelProps = {
  title: string
  subtitle?: string
  actions?: ReactNode
  className?: string
  children: ReactNode
}

// HUD-framed section with a heading. The heading names the section for screen readers.
function Panel({ title, subtitle, actions, className = '', children }: PanelProps) {
  const headingId = useId()
  return (
    <section aria-labelledby={headingId} className={`hud-panel ${className}`}>
      <header className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id={headingId} className="hud-heading">{title}</h2>
          {subtitle && <p className="mt-1 text-xs text-hud-muted">{subtitle}</p>}
        </div>
        {actions}
      </header>
      {children}
    </section>
  )
}

export default Panel
