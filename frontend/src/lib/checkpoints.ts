import type { Checkpoint } from '../api/types'
import { formatDateTime } from './datetime'
import { HAZARD_LABELS, riskLabel } from './risk'

export interface DetailRow {
  label: string
  value: string
}

/** Rows shown for a checkpoint in the map popup and the sidebar list. */
export function checkpointRows(cp: Checkpoint): DetailRow[] {
  const rows: DetailRow[] = [
    { label: 'Mile', value: `${cp.mile.toFixed(1)} (covers mi ${cp.segment_start_mile.toFixed(1)}–${cp.segment_end_mile.toFixed(1)})` },
    { label: 'ETA', value: formatDateTime(cp.eta) },
    { label: 'Forecast hour', value: formatDateTime(cp.forecast_time) },
  ]
  if (!cp.weather || !cp.risk) {
    rows.push({ label: 'Risk', value: 'Unknown: forecast unavailable' })
    return rows
  }
  const gust = cp.weather.wind_gust_mph === null ? '' : `, gusts ${cp.weather.wind_gust_mph.toFixed(0)} mph`
  const windRisk = cp.risk.load_rule_applied
    ? `${riskLabel(cp.risk.wind_before_load_rule)} → ${riskLabel(cp.risk.wind)} (load rule)`
    : riskLabel(cp.risk.wind)
  rows.push(
    { label: 'Wind', value: `${cp.weather.wind_mph.toFixed(0)} mph${gust} · ${windRisk}` },
    { label: 'Rain', value: `${cp.weather.rain_in_per_hr.toFixed(2)} in/hr · ${riskLabel(cp.risk.rain)}` },
    { label: 'Snow', value: `${cp.weather.snow_in_per_hr.toFixed(2)} in/hr · ${riskLabel(cp.risk.snow)}` },
    {
      label: 'Risk',
      value: cp.hazards.length
        ? `${riskLabel(cp.risk.overall)} (${cp.hazards.map((h) => HAZARD_LABELS[h]).join(', ')})`
        : riskLabel(cp.risk.overall),
    },
  )
  return rows
}
