/**
 * Deterministic API fixtures for browser tests. They have the exact shape the
 * Django API returns, and their values are internally consistent: segments tile
 * each route, summaries and ranking are computed from the checkpoints, and
 * heatmap codes match their wind/rain/snow values. TEST DATA ONLY: never used
 * by the application itself.
 */
import type {
  Checkpoint,
  CheckpointRisk,
  HazardStretch,
  Heatmap,
  Place,
  RiskCode,
  RiskSummary,
  RouteOption,
  TripPlanResponse,
} from '../src/api/types.ts'

export const DEPARTURE = '2026-10-25T13:20:00.000Z'
const LEVELS: RiskCode[] = ['low', 'moderate', 'high', 'severe', 'no_travel']
const MILE_M = 1609.344

export const PLACES: Record<string, Place> = {
  dallas: { id: 'p-dallas', label: 'Dallas, TX', lat: 32.7767, lon: -96.797, kind: 'Municipality' },
  denver: { id: 'p-denver', label: 'Denver, CO', lat: 39.7392, lon: -104.9903, kind: 'Municipality' },
  dalhart: { id: 'p-dalhart', label: 'Dalhart, TX', lat: 36.0595, lon: -102.5132, kind: 'Municipality' },
}

export function geocodeResults(query: string): Place[] {
  const q = query.toLowerCase()
  return Object.values(PLACES).filter((p) => p.label.toLowerCase().startsWith(q.slice(0, 3)))
}

function haversineMiles(a: [number, number], b: [number, number]): number {
  const rad = Math.PI / 180
  const dLat = (b[1] - a[1]) * rad
  const dLon = (b[0] - a[0]) * rad
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a[1] * rad) * Math.cos(b[1] * rad) * Math.sin(dLon / 2) ** 2
  return (2 * 6_371_008.8 * Math.asin(Math.sqrt(h))) / MILE_M
}

// Weather values that fall unambiguously inside each assessment band (load 38,000 lb).
const WEATHER: Record<RiskCode, { wind: number; gust: number; rain: number; snow: number; risk: CheckpointRisk }> = {
  low: { wind: 9, gust: 15, rain: 0, snow: 0, risk: risk('low', 'low', 'low', 'low') },
  moderate: { wind: 28.4, gust: 39, rain: 0.02, snow: 0, risk: risk('moderate', 'moderate', 'low', 'low') },
  high: { wind: 12, gust: 20, rain: 0.31, snow: 0, risk: risk('high', 'low', 'high', 'low') },
  severe: { wind: 14, gust: 22, rain: 0, snow: 2.4, risk: risk('severe', 'low', 'low', 'severe') },
  // 47 mph is Severe wind; with > 30,000 lb the load rule makes it No Travel.
  no_travel: { wind: 47, gust: 63, rain: 0, snow: 0, risk: { ...risk('no_travel', 'no_travel', 'low', 'low'), wind_before_load_rule: 'severe', load_rule_applied: true } },
}

function risk(overall: RiskCode, wind: RiskCode, rain: RiskCode, snow: RiskCode): CheckpointRisk {
  return { overall, wind, wind_before_load_rule: wind, rain, snow, load_rule_applied: false }
}

function hourContaining(ms: number): string {
  const h = 3_600_000
  return new Date(Math.ceil(ms / h) * h).toISOString()
}

type Pattern = (index: number) => RiskCode | null

function buildRoute(index: number, path: [number, number][], hours: number, pattern: Pattern): RouteOption {
  const cumulative = [0]
  for (let i = 1; i < path.length; i++) cumulative.push(cumulative[i - 1] + haversineMiles(path[i - 1], path[i]))
  const total = cumulative[cumulative.length - 1]
  const marks: number[] = []
  for (let m = 0; m < total; m += 25) marks.push(m)
  marks.push(total)
  const departMs = Date.parse(DEPARTURE)

  const checkpoints: Checkpoint[] = marks.map((mile, i) => {
    let s = 1
    while (s < cumulative.length - 1 && cumulative[s] < mile) s++
    const f = (mile - cumulative[s - 1]) / (cumulative[s] - cumulative[s - 1] || 1)
    const lon = path[s - 1][0] + (path[s][0] - path[s - 1][0]) * f
    const lat = path[s - 1][1] + (path[s][1] - path[s - 1][1]) * f
    const etaMs = departMs + (mile / total) * hours * 3_600_000
    const start = i === 0 ? 0 : (marks[i - 1] + mile) / 2
    const end = i === marks.length - 1 ? total : (mile + marks[i + 1]) / 2
    const level = pattern(i)
    const w = level ? WEATHER[level] : null
    return {
      index: i,
      mile: Math.round(mile * 100) / 100,
      segment_start_mile: start,
      segment_end_mile: end,
      segment_miles: end - start,
      lat,
      lon,
      eta: new Date(etaMs).toISOString(),
      forecast_time: hourContaining(etaMs),
      status: level ? 'ok' : 'unavailable',
      weather: w ? { wind_mph: w.wind, wind_gust_mph: w.gust, rain_in_per_hr: w.rain, snow_in_per_hr: w.snow } : null,
      risk: w ? w.risk : null,
      hazards: level && level !== 'low' ? (['wind', 'rain', 'snow'] as const).filter((h) => w!.risk[h] === level) : [],
      warnings: level
        ? [
            ...(level === 'no_travel'
              ? ['Load rule: 38,000 lb with 47 mph wind raises wind risk from Severe to No Travel.', 'No Travel: wind 47 mph.']
              : []),
          ]
        : ['Forecast unavailable for this arrival time: risk is unknown, not low.'],
    }
  })

  return {
    id: `rt_fixture${index}`,
    index,
    label: `Route ${'ABC'[index]}`,
    distance_meters: Math.round(total * MILE_M),
    distance_miles: Math.round(total * 10) / 10,
    duration_seconds: Math.round(hours * 3600),
    traffic_delay_seconds: index === 0 ? 240 : 0,
    departure_time: DEPARTURE,
    arrival_time: checkpoints[checkpoints.length - 1].eta,
    geometry: { type: 'LineString', coordinates: path },
    geometry_point_count: { provider: path.length * 50, display: path.length },
    eta_source: 'provider_timing',
    checkpoints,
    risk_summary: summarize(checkpoints),
    hazard_stretches: stretches(checkpoints),
    rank: null,
    recommended: false,
  }
}

function summarize(checkpoints: Checkpoint[]): RiskSummary | null {
  const miles = Object.fromEntries(LEVELS.map((l) => [l, 0])) as Record<RiskCode, number>
  let unknown = 0
  let weighted = 0
  for (const cp of checkpoints) {
    if (!cp.risk) unknown += cp.segment_miles
    else {
      miles[cp.risk.overall] += cp.segment_miles
      weighted += cp.segment_miles * LEVELS.indexOf(cp.risk.overall)
    }
  }
  const known = LEVELS.reduce((sum, l) => sum + miles[l], 0)
  if (known === 0) return null
  return {
    total_miles: known + unknown,
    miles_by_level: miles,
    unknown_miles: unknown,
    severe_or_worse_miles: miles.severe + miles.no_travel,
    average_risk: weighted / known,
    max_risk: [...LEVELS].reverse().find((l) => miles[l] > 0) ?? null,
    has_no_travel: miles.no_travel > 0,
    coverage_complete: unknown === 0,
  }
}

function stretches(checkpoints: Checkpoint[]): HazardStretch[] {
  const out: HazardStretch[] = []
  for (const cp of checkpoints) {
    const level = cp.risk?.overall
    if (level !== 'high' && level !== 'severe' && level !== 'no_travel') continue
    const last = out[out.length - 1]
    if (last && last.level === level && last.last_index === cp.index - 1) {
      Object.assign(last, { end_mile: cp.segment_end_mile, last_eta: cp.eta, last_index: cp.index })
    } else {
      out.push({ level, hazards: cp.hazards, start_mile: cp.segment_start_mile, end_mile: cp.segment_end_mile,
        first_eta: cp.eta, last_eta: cp.eta, first_index: cp.index, last_index: cp.index })
    }
  }
  return out
}

function rankKey(route: RouteOption): number[] {
  const s = route.risk_summary!
  return [Number(s.has_no_travel), s.severe_or_worse_miles, s.miles_by_level.high, s.average_risk ?? Infinity, route.duration_seconds]
}

function buildHeatmap(routes: RouteOption[], unavailable: boolean): Heatmap {
  const spacing = 0.5
  const lats: number[] = []
  const lons: number[] = []
  for (let lat = 32.5; lat <= 40; lat += spacing) {
    for (let lon = -105; lon <= -96.5; lon += spacing) {
      const near = routes.some((r) => r.geometry.coordinates.some(([x, y]) => Math.abs(x - lon) < 1.2 && Math.abs(y - lat) < 1.2))
      if (near) {
        lats.push(lat)
        lons.push(lon)
      }
    }
  }
  const frames = Array.from({ length: 49 }, (_, f) => f)
  const code = (f: number, p: number) => (unavailable || (p + f) % 9 === 8 ? null : (p + f) % 5)
  const value = (f: number, p: number, key: 'wind' | 'rain' | 'snow') => {
    const c = code(f, p)
    return c === null ? null : WEATHER[LEVELS[c]][key]
  }
  return {
    status: unavailable ? 'unavailable' : 'partial',
    spacing_degrees: spacing,
    frame_offsets_hours: frames,
    frame_times: frames.map((f) => hourContaining(Date.parse(DEPARTURE) + f * 3_600_000)),
    lats,
    lons,
    risk: frames.map((f) => lats.map((_, p) => code(f, p))),
    wind_mph: frames.map((f) => lats.map((_, p) => value(f, p, 'wind'))),
    rain_in_per_hr: frames.map((f) => lats.map((_, p) => value(f, p, 'rain'))),
    snow_in_per_hr: frames.map((f) => lats.map((_, p) => value(f, p, 'snow'))),
  }
}

const PATHS: [number, number][][] = [
  [[-96.797, 32.7767], [-97.5, 35.47], [-99.2, 37.0], [-102.0, 38.7], [-104.99, 39.7392]],
  [[-96.797, 32.7767], [-98.5, 33.9], [-101.83, 35.2], [-103.9, 37.6], [-104.99, 39.7392]],
  [[-96.797, 32.7767], [-98.0, 34.5], [-100.5, 36.5], [-103.0, 38.2], [-104.99, 39.7392]],
]

export function planFixture(options: { weatherUnavailable?: boolean; label?: string } = {}): TripPlanResponse {
  const unknownOnly: Pattern = () => null
  const patterns: Pattern[] = options.weatherUnavailable
    ? [unknownOnly, unknownOnly, unknownOnly]
    : [
        (i) => (i === 8 || i === 9 ? 'no_travel' : i === 14 ? 'moderate' : 'low'),
        (i) => (i === 3 || i === 4 ? 'moderate' : i === 12 ? 'high' : 'low'),
        (i) => (i === 5 ? null : i === 10 ? 'moderate' : 'low'),
      ]
  const routes = PATHS.map((path, i) => buildRoute(i, path, [12.1, 12.7, 13.5][i], patterns[i]))

  let recommendation: TripPlanResponse['recommendation']
  if (options.weatherUnavailable) {
    routes.forEach((r) => (r.risk_summary = null))
    recommendation = {
      status: 'unavailable', route_id: null, route_label: null, ranked_route_ids: [], decided_by: null,
      explanation: 'The weather provider did not respond in time. Route risk cannot be assessed; no route is recommended.',
      warnings: [], coverage_complete: false,
    }
  } else {
    const ranked = [...routes].sort((a, b) => {
      const ka = rankKey(a)
      const kb = rankKey(b)
      for (let i = 0; i < ka.length; i++) if (ka[i] !== kb[i]) return ka[i] - kb[i]
      return a.index - b.index
    })
    ranked.forEach((r, i) => {
      r.rank = i + 1
      r.recommended = i === 0
    })
    const missing = routes.filter((r) => (r.risk_summary?.unknown_miles ?? 0) > 0).map((r) => r.label)
    recommendation = {
      status: 'recommended',
      route_id: ranked[0].id,
      route_label: ranked[0].label,
      ranked_route_ids: ranked.map((r) => r.id),
      decided_by: 'high_miles',
      explanation: `${ranked[0].label} ties on Severe miles (0.0 mi) and has the fewest High miles.`,
      warnings: missing.length
        ? [`Forecast data is missing for part of ${missing.join(', ')}; those miles are unknown, not low risk, and are excluded from the ranking.`]
        : [],
      coverage_complete: missing.length === 0,
    }
  }

  const total = routes.reduce((n, r) => n + r.checkpoints.length, 0)
  const known = routes.reduce((n, r) => n + r.checkpoints.filter((c) => c.status === 'ok').length, 0)
  return {
    routes,
    route_count: 3,
    requested_route_count: 3,
    notice: null,
    recommendation,
    weather_risk: {
      status: known === total ? 'complete' : known === 0 ? 'unavailable' : 'partial',
      message: known === 0
        ? 'The weather provider did not respond in time. Route risk cannot be assessed; no route is recommended.'
        : `Forecasts are missing for ${total - known} of ${total} checkpoints; those segments are unknown risk, not low risk.`,
      provider: 'Open-Meteo',
      checkpoints_total: total,
      checkpoints_with_forecast: known,
      window_start: DEPARTURE,
      window_end: DEPARTURE,
    },
    heatmap: buildHeatmap(routes, Boolean(options.weatherUnavailable)),
    inputs: {
      origin: { lat: PLACES.dallas.lat, lon: PLACES.dallas.lon, label: PLACES.dallas.label },
      destination: { lat: PLACES.denver.lat, lon: PLACES.denver.lon, label: options.label ?? PLACES.denver.label },
      departure_time: DEPARTURE,
      load_weight_lb: 38000,
      checkpoint_interval_miles: 25,
    },
    provider: { routing: 'TomTom', travel_mode: 'truck', weather: 'Open-Meteo' },
  }
}
