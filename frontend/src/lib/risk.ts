import type { Hazard, RiskCode } from '../api/types'

// One risk palette for checkpoints, heatmap, badges and legend. Hues are kept
// apart from the route identity colours (blue / purple / dark cyan).
export const RISK_LEVELS: { code: RiskCode; score: number; label: string; color: string }[] = [
  { code: 'low', score: 0, label: 'Low', color: '#16a34a' },
  { code: 'moderate', score: 1, label: 'Moderate', color: '#eab308' },
  { code: 'high', score: 2, label: 'High', color: '#f97316' },
  { code: 'severe', score: 3, label: 'Severe', color: '#dc2626' },
  { code: 'no_travel', score: 4, label: 'No Travel', color: '#4c0519' },
]

/** Missing forecast: never shown in a risk colour, never labelled Low. */
export const UNKNOWN_COLOR = '#9ca3af'
export const UNKNOWN_LABEL = 'No forecast'

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
