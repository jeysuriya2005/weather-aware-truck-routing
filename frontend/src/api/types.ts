// Shapes returned by the Django API (backend/trips/presenters.py).

export interface Place {
  id: string
  label: string
  lat: number
  lon: number
  kind: string
}

export interface LocationInput {
  lat: number
  lon: number
  label: string
}

export type CheckpointIntervalMiles = 10 | 25 | 50

export interface TripPlanRequest {
  origin: LocationInput
  destination: LocationInput
  /** ISO 8601 with UTC offset. */
  departure_time: string
  load_weight_lb: number
  checkpoint_interval_miles: CheckpointIntervalMiles
}

export type RiskCode = 'low' | 'moderate' | 'high' | 'severe' | 'no_travel'
export type Hazard = 'wind' | 'rain' | 'snow'

export interface CheckpointWeather {
  wind_mph: number
  wind_gust_mph: number | null
  rain_in_per_hr: number
  snow_in_per_hr: number
}

export interface CheckpointRisk {
  overall: RiskCode
  wind: RiskCode
  wind_before_load_rule: RiskCode
  rain: RiskCode
  snow: RiskCode
  load_rule_applied: boolean
}

export interface Checkpoint {
  index: number
  mile: number
  segment_start_mile: number
  segment_end_mile: number
  segment_miles: number
  lat: number
  lon: number
  eta: string
  forecast_time: string
  status: 'ok' | 'unavailable'
  weather: CheckpointWeather | null
  risk: CheckpointRisk | null
  hazards: Hazard[]
  warnings: string[]
}

export interface RiskSummary {
  total_miles: number
  miles_by_level: Record<RiskCode, number>
  unknown_miles: number
  severe_or_worse_miles: number
  /** 0 (Low) .. 4 (No Travel), distance-weighted over known miles. */
  average_risk: number | null
  max_risk: RiskCode | null
  has_no_travel: boolean
  coverage_complete: boolean
}

export interface HazardStretch {
  level: 'high' | 'severe' | 'no_travel'
  hazards: Hazard[]
  start_mile: number
  end_mile: number
  first_eta: string
  last_eta: string
  first_index: number
  last_index: number
}

export interface RouteOption {
  id: string
  index: number
  label: string
  distance_meters: number
  distance_miles: number
  duration_seconds: number
  traffic_delay_seconds: number
  departure_time: string
  arrival_time: string
  geometry: {
    type: 'LineString'
    /** [longitude, latitude] pairs, simplified for display. */
    coordinates: [number, number][]
  }
  geometry_point_count: { provider: number; display: number }
  eta_source: 'provider_timing' | 'proportional_estimate'
  checkpoints: Checkpoint[]
  risk_summary: RiskSummary | null
  hazard_stretches: HazardStretch[]
  rank: number | null
  recommended: boolean
}

export interface Recommendation {
  status: 'recommended' | 'no_safe_route' | 'unavailable'
  route_id: string | null
  route_label: string | null
  ranked_route_ids: string[]
  decided_by: string | null
  explanation: string
  warnings: string[]
  coverage_complete: boolean
}

export interface WeatherRiskStatus {
  status: 'complete' | 'partial' | 'unavailable'
  message: string
  provider: string
  checkpoints_total: number
  checkpoints_with_forecast: number
  window_start: string | null
  window_end: string | null
}

export interface Heatmap {
  status: 'complete' | 'partial' | 'unavailable'
  spacing_degrees: number
  frame_offsets_hours: number[]
  frame_times: string[]
  lats: number[]
  lons: number[]
  /** risk[frame][point]: 0 Low .. 4 No Travel, null = forecast unavailable. */
  risk: (number | null)[][]
  wind_mph: (number | null)[][]
  rain_in_per_hr: (number | null)[][]
  snow_in_per_hr: (number | null)[][]
}

export interface TripPlanResponse {
  routes: RouteOption[]
  route_count: number
  requested_route_count: number
  notice: string | null
  recommendation: Recommendation
  weather_risk: WeatherRiskStatus
  heatmap: Heatmap
  inputs: TripPlanRequest
  provider: { routing: string; travel_mode: string; weather: string }
}

export interface ApiErrorBody {
  error: {
    code: string
    message: string
    fields?: Record<string, unknown>
  }
}
