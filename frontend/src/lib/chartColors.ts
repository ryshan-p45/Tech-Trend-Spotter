import type { SourceType } from '../api/types.ts'

/*
 * Data colours for charts, one per source type. Fixed per entity (never by rank), so
 * "advisories are magenta" holds on every chart and after any filter.
 *
 * Validated with the dataviz palette checker against the HUD panel colour (#0c1f33):
 * lightness band, chroma, colour-blind separation (worst ΔE 9.2) and contrast all pass.
 * Stack/legend order is web -> advisory -> social, the order the adjacent pairs were checked in.
 * These are for marks only - text always uses the hud-text / hud-muted tokens.
 */
export const SOURCE_TYPE_COLORS: Record<SourceType, string> = {
  web: '#1299b4',
  advisory: '#e8457a',
  social: '#bf7f1a',
}

export const SOURCE_TYPE_ORDER: SourceType[] = ['web', 'advisory', 'social']

// Chart chrome, one step off the panel surface (hairline grid/axes)
export const CHART_SURFACE = '#0c1f33'
export const CHART_GRID = '#173550'
export const CHART_AXIS_TEXT = '#6f93a8'
export const CHART_TEXT = '#c9e6f2'
