import type { Hazard, RiskCode } from '../api/types'

// One risk palette for checkpoints, heatmap, badges and legend. Hues are kept
// apart from the route identity colours (blue / purple / dark cyan).
// `color` is the map/legend colour; `tint` + `ink` are the accessible badge
// background and text (ink on tint >= 4.5:1 contrast).
export const RISK_LEVELS: { code: RiskCode; score: number; label: string; color: string; tint: string; ink: string }[] = [
  { code: 'low', score: 0, label: 'Low', color: '#16a34a', tint: '#dcfce7', ink: '#14532d' },
  { code: 'moderate', score: 1, label: 'Moderate', color: '#eab308', tint: '#fef9c3', ink: '#713f12' },
  { code: 'high', score: 2, label: 'High', color: '#f97316', tint: '#ffedd5', ink: '#7c2d12' },
  { code: 'severe', score: 3, label: 'Severe', color: '#dc2626', tint: '#fee2e2', ink: '#7f1d1d' },
  { code: 'no_travel', score: 4, label: 'No Travel', color: '#4c0519', tint: '#4c0519', ink: '#ffffff' },
]

/** Missing forecast: never shown in a risk colour, never labelled Low. */
export const UNKNOWN_COLOR = '#9ca3af'
export const UNKNOWN_TINT = '#f1f5f9'
export const UNKNOWN_INK = '#475569'
export const UNKNOWN_LABEL = 'No forecast'

export function riskTint(code: RiskCode | null): { background: string; color: string } {
  const level = RISK_LEVELS.find((l) => l.code === code)
  return level ? { background: level.tint, color: level.ink } : { background: UNKNOWN_TINT, color: UNKNOWN_INK }
}

export function riskLabel(code: RiskCode | null): string {
  return RISK_LEVELS.find((level) => level.code === code)?.label ?? UNKNOWN_LABEL
}

export function riskColor(code: RiskCode | null): string {
  return RISK_LEVELS.find((level) => level.code === code)?.color ?? UNKNOWN_COLOR
}

export function riskCodeFromScore(score: number | null): RiskCode | null {
  return RISK_LEVELS.find((level) => level.score === score)?.code ?? null
}

/** Light text on dark risk colours for contrast. */
export function riskTextColor(code: RiskCode | null): string {
  return code === 'severe' || code === 'no_travel' ? '#ffffff' : '#1f2933'
}

export const HAZARD_LABELS: Record<Hazard, string> = { wind: 'Wind', rain: 'Rain', snow: 'Snow' }

export function formatAverageRisk(score: number | null): string {
  if (score === null) return 'Unknown'
  return `${score.toFixed(2)} / 4`
}
