import type { ExpressionSpecification } from 'maplibre-gl'
import type { FeatureCollection, Point } from 'geojson'
import type { Heatmap } from '../api/types'
import { RISK_LEVELS, UNKNOWN_COLOR } from './risk'

/** Property name holding a point's risk score for a frame (-1 = no forecast). */
export const frameProperty = (frame: number) => `r${frame}`
const UNKNOWN_SCORE = -1

/**
 * All 49 frames are stored as properties of each point, so moving the slider
 * only swaps the style expression; no data is re-uploaded to the map.
 */
export function heatmapFeatures(heatmap: Heatmap): FeatureCollection<Point> {
  return {
    type: 'FeatureCollection',
    features: heatmap.lats.map((lat, i) => {
      const properties: Record<string, number> = { i }
      heatmap.risk.forEach((frame, f) => {
        properties[frameProperty(f)] = frame[i] ?? UNKNOWN_SCORE
      })
      return {
        type: 'Feature',
        properties,
        geometry: { type: 'Point', coordinates: [heatmap.lons[i], lat] },
      }
    }),
  }
}

/**
 * ['match', input, key1, color1, ..., fallback] mapping risk keys to the shared
 * palette. MapLibre's tuple types cannot express a spread-built match, hence
 * the single cast here.
 */
export function riskColorMatch(input: ExpressionSpecification, key: 'score' | 'code'): ExpressionSpecification {
  const stops = RISK_LEVELS.flatMap((level) => [level[key], level.color])
  return ['match', input, ...stops, UNKNOWN_COLOR] as unknown as ExpressionSpecification
}

export function heatmapColorExpression(frame: number): ExpressionSpecification {
  return riskColorMatch(['get', frameProperty(frame)], 'score')
}

/**
 * Unknown cells stay visible but faint, so gaps read as "no data", not "clear".
 * Kept below the route lines' opacity so routes and checkpoints stay legible on top.
 */
export const HEATMAP_OPACITY = { known: 0.36, unknown: 0.2 }

export function heatmapOpacityExpression(frame: number): ExpressionSpecification {
  return ['case', ['==', ['get', frameProperty(frame)], UNKNOWN_SCORE], HEATMAP_OPACITY.unknown, HEATMAP_OPACITY.known]
}

const EARTH_METERS_PER_PIXEL_Z0 = 78_271.517 // MapLibre 512 px tiles at the equator

/**
 * Circle radius (px) per zoom so each cell visually covers its grid square,
 * slightly overlapping its neighbours for a continuous heatmap look.
 */
export function heatmapRadiusExpression(spacingDegrees: number, latitude: number): ExpressionSpecification {
  const radiusMeters = spacingDegrees * 111_320
  const pxAtZ0 = radiusMeters / (EARTH_METERS_PER_PIXEL_Z0 * Math.cos((latitude * Math.PI) / 180))
  return ['interpolate', ['exponential', 2], ['zoom'], 0, pxAtZ0, 16, pxAtZ0 * 2 ** 16]
}

export function meanLatitude(heatmap: Heatmap): number {
  if (heatmap.lats.length === 0) return 0
  return heatmap.lats.reduce((sum, lat) => sum + lat, 0) / heatmap.lats.length
}

export interface FrameLabel {
  offsetHours: number
  /** Departure + offset: the moment the slider refers to. */
  moment: string
  /** Forecast record used: the UTC hour whose preceding-hour period contains `moment`. */
  forecastHour: string | undefined
}

/**
 * Keeps "departure + N h" and the forecast hour apart: a 13:20 departure at
 * +0 h uses the 14:00 forecast record, so labelling +0 h as 14:00 would be wrong.
 */
export function frameLabel(heatmap: Heatmap, departureIso: string, frame: number): FrameLabel {
  const offsetHours = heatmap.frame_offsets_hours[frame] ?? frame
  const moment = new Date(new Date(departureIso).getTime() + offsetHours * 3_600_000).toISOString()
  return { offsetHours, moment, forecastHour: heatmap.frame_times[frame] }
}

/**
 * The overlay frame that uses the same forecast hour as a checkpoint's ETA
 * (frame h = hour containing departure + h; checkpoint = hour containing its ETA),
 * or null if the ETA is beyond the 0-48 h overlay.
 */
export function frameForForecastHour(heatmap: Heatmap, forecastTimeIso: string): number | null {
  const target = Date.parse(forecastTimeIso)
  const index = heatmap.frame_times.findIndex((time) => Date.parse(time) === target)
  return index === -1 ? null : index
}

export interface CellForecast {
  index: number
  lat: number
  lon: number
  risk: number | null
  windMph: number | null
  rainInPerHr: number | null
  snowInPerHr: number | null
}

/** The forecast values the overlay shows for one corridor cell at one frame. */
export function cellForecast(heatmap: Heatmap, index: number, frame: number): CellForecast {
  return {
    index,
    lat: heatmap.lats[index],
    lon: heatmap.lons[index],
    risk: heatmap.risk[frame]?.[index] ?? null,
    windMph: heatmap.wind_mph[frame]?.[index] ?? null,
    rainInPerHr: heatmap.rain_in_per_hr[frame]?.[index] ?? null,
    snowInPerHr: heatmap.snow_in_per_hr[frame]?.[index] ?? null,
  }
}

/** Share of points with a forecast in a frame, for status text. */
export function frameCoverage(heatmap: Heatmap, frame: number): number {
  const values = heatmap.risk[frame] ?? []
  if (values.length === 0) return 0
  return values.filter((value) => value !== null).length / values.length
}
