import type { Checkpoint, RiskCode, RouteOption } from '../api/types'
import { RISK_LEVELS } from './risk'

/**
 * Per-route weather summary derived ONLY from the API's checkpoint data.
 * Peaks consider checkpoints with a forecast; a route without any forecast
 * yields nulls (shown as "no forecast"), never zeros.
 */
export interface Peak {
  value: number
  checkpoint: Checkpoint
}

export interface DistributionSlice {
  code: RiskCode | 'unknown'
  miles: number
  share: number
}

export interface RouteInsights {
  peakWind: Peak | null
  peakGust: Peak | null
  peakRain: Peak | null
  peakSnow: Peak | null
  worst: RiskCode | null
  highOrWorseMiles: number | null
  checkpointsWithForecast: number
  checkpointsTotal: number
  distribution: DistributionSlice[]
}

function peak(checkpoints: Checkpoint[], value: (cp: Checkpoint) => number | null): Peak | null {
  let best: Peak | null = null
  for (const cp of checkpoints) {
    const v = cp.weather ? value(cp) : null
    if (v === null) continue
    if (!best || v > best.value) best = { value: v, checkpoint: cp }
  }
  return best
}

export function routeInsights(route: RouteOption): RouteInsights {
  const known = route.checkpoints.filter((cp) => cp.status === 'ok' && cp.weather && cp.risk)
  const summary = route.risk_summary
  const total = route.checkpoints.reduce((sum, cp) => sum + cp.segment_miles, 0)

  const slices: DistributionSlice[] = []
  if (summary) {
    for (const level of RISK_LEVELS) {
      const miles = summary.miles_by_level[level.code]
      if (miles > 0) slices.push({ code: level.code, miles, share: miles / summary.total_miles })
    }
    if (summary.unknown_miles > 0) {
      slices.push({ code: 'unknown', miles: summary.unknown_miles, share: summary.unknown_miles / summary.total_miles })
    }
  } else if (total > 0) {
    slices.push({ code: 'unknown', miles: total, share: 1 })
  }

  return {
    peakWind: peak(known, (cp) => cp.weather!.wind_mph),
    peakGust: peak(known, (cp) => cp.weather!.wind_gust_mph),
    peakRain: peak(known, (cp) => cp.weather!.rain_in_per_hr),
    peakSnow: peak(known, (cp) => cp.weather!.snow_in_per_hr),
    worst: summary?.max_risk ?? null,
    highOrWorseMiles: summary ? summary.miles_by_level.high + summary.severe_or_worse_miles : null,
    checkpointsWithForecast: known.length,
    checkpointsTotal: route.checkpoints.length,
    distribution: slices,
  }
}

/** "100%", "97%", "<1%" (never rounds a non-zero share down to 0%). */
export function formatShare(share: number): string {
  if (share > 0 && share < 0.01) return '<1%'
  if (share < 1 && share > 0.99) return '>99%'
  return `${Math.round(share * 100)}%`
}
