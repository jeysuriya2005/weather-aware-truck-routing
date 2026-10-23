import type { Checkpoint, Heatmap, RiskSummary, RouteOption, TripPlanResponse } from '../api/types'

export function checkpoint(overrides: Partial<Checkpoint> = {}): Checkpoint {
  return {
    index: 0,
    mile: 0,
    segment_start_mile: 0,
    segment_end_mile: 12.5,
    segment_miles: 12.5,
    lat: 32.78,
    lon: -96.8,
    eta: '2026-10-25T13:00:00+00:00',
    forecast_time: '2026-10-25T13:00:00+00:00',
    status: 'ok',
    weather: { wind_mph: 8, wind_gust_mph: 14, rain_in_per_hr: 0, snow_in_per_hr: 0 },
    risk: {
      overall: 'low',
      wind: 'low',
      wind_before_load_rule: 'low',
      rain: 'low',
      snow: 'low',
      load_rule_applied: false,
    },
    hazards: [],
    warnings: [],
    ...overrides,
  }
}

export const UNAVAILABLE_CHECKPOINT = checkpoint({
  index: 1,
  mile: 25,
  status: 'unavailable',
  weather: null,
  risk: null,
  warnings: ['Forecast unavailable for this arrival time: risk is unknown, not low.'],
})

export function summary(overrides: Partial<RiskSummary> = {}): RiskSummary {
  return {
    total_miles: 100,
    miles_by_level: { low: 100, moderate: 0, high: 0, severe: 0, no_travel: 0 },
    unknown_miles: 0,
    severe_or_worse_miles: 0,
    average_risk: 0,
    max_risk: 'low',
    has_no_travel: false,
    coverage_complete: true,
    ...overrides,
  }
}

export function route(index: number, overrides: Partial<RouteOption> = {}): RouteOption {
  return {
    id: `rt_${index}`,
    index,
    label: `Route ${'ABC'[index]}`,
    distance_meters: 160934.4,
    distance_miles: 100,
    duration_seconds: 7200,
    traffic_delay_seconds: 0,
    departure_time: '2026-10-25T13:00:00+00:00',
    arrival_time: '2026-10-25T15:00:00+00:00',
    geometry: { type: 'LineString', coordinates: [[-96.8, 32.78], [-97.0, 33.0]] },
    geometry_point_count: { provider: 100, display: 2 },
    eta_source: 'provider_timing',
    checkpoints: [checkpoint()],
    risk_summary: summary(),
    hazard_stretches: [],
    rank: index + 1,
    recommended: index === 0,
    ...overrides,
  }
}

export function heatmap(frames = 49, points = 3): Heatmap {
  const risk = Array.from({ length: frames }, (_, f) =>
    Array.from({ length: points }, (_, p) => (p === points - 1 && f % 2 === 1 ? null : (f + p) % 5)),
  )
  return {
    status: 'partial',
    spacing_degrees: 0.25,
    frame_offsets_hours: Array.from({ length: frames }, (_, f) => f),
    frame_times: Array.from({ length: frames }, (_, f) => new Date(Date.UTC(2026, 9, 25, 13 + f)).toISOString()),
    lats: Array.from({ length: points }, (_, p) => 32 + p),
    lons: Array.from({ length: points }, (_, p) => -97 - p),
    risk,
    wind_mph: risk.map((frame) => frame.map((v) => (v === null ? null : 10))),
    rain_in_per_hr: risk.map((frame) => frame.map((v) => (v === null ? null : 0))),
    snow_in_per_hr: risk.map((frame) => frame.map((v) => (v === null ? null : 0))),
  }
}

export function plan(overrides: Partial<TripPlanResponse> = {}): TripPlanResponse {
  const routes = overrides.routes ?? [route(0), route(1)]
  return {
    routes,
    route_count: routes.length,
    requested_route_count: 3,
    notice: null,
    recommendation: {
      status: 'recommended',
      route_id: routes[0].id,
      route_label: routes[0].label,
      ranked_route_ids: routes.map((r) => r.id),
      decided_by: 'travel_time',
      explanation: 'Route A ties on all weather-risk criteria and is the fastest.',
      warnings: [],
      coverage_complete: true,
    },
    weather_risk: {
      status: 'complete',
      message: 'Forecasts are available for every checkpoint.',
      provider: 'Open-Meteo',
      checkpoints_total: 2,
      checkpoints_with_forecast: 2,
      window_start: null,
      window_end: null,
    },
    heatmap: heatmap(),
    inputs: {
      origin: { lat: 32.78, lon: -96.8, label: 'Dallas, TX' },
      destination: { lat: 39.74, lon: -104.99, label: 'Denver, CO' },
      departure_time: '2026-10-25T13:00:00Z',
      load_weight_lb: 38000,
      checkpoint_interval_miles: 25,
    },
    provider: { routing: 'TomTom', travel_mode: 'truck', weather: 'Open-Meteo' },
    ...overrides,
  }
}
