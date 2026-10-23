import { describe, expect, it } from 'vitest'
import { checkpoint, UNAVAILABLE_CHECKPOINT, heatmap } from '../test/fixtures'
import { checkpointRows } from './checkpoints'
import {
  frameCoverage,
  frameProperty,
  heatmapColorExpression,
  heatmapFeatures,
  heatmapOpacityExpression,
  heatmapRadiusExpression,
} from './heatmap'
import { RISK_LEVELS, UNKNOWN_COLOR, UNKNOWN_LABEL, formatAverageRisk, riskCodeFromScore, riskColor, riskLabel } from './risk'
import { ROUTE_COLORS } from './routeColors'

describe('risk palette', () => {
  it('orders levels by the backend score', () => {
    expect(RISK_LEVELS.map((l) => [l.code, l.score])).toEqual([
      ['low', 0],
      ['moderate', 1],
      ['high', 2],
      ['severe', 3],
      ['no_travel', 4],
    ])
  })

  it('keeps risk colours distinct from route colours and from "no forecast"', () => {
    const riskColors = RISK_LEVELS.map((l) => l.color)
    expect(new Set(riskColors).size).toBe(5)
    for (const color of ROUTE_COLORS) expect(riskColors).not.toContain(color)
    expect(riskColors).not.toContain(UNKNOWN_COLOR)
  })

  it('never labels missing data as Low', () => {
    expect(riskLabel(null)).toBe(UNKNOWN_LABEL)
    expect(riskColor(null)).toBe(UNKNOWN_COLOR)
    expect(riskColor(null)).not.toBe(riskColor('low'))
    expect(riskCodeFromScore(null)).toBeNull()
    expect(riskCodeFromScore(4)).toBe('no_travel')
    expect(formatAverageRisk(null)).toBe('Unknown')
    expect(formatAverageRisk(0.025)).toBe('0.03 / 4')
  })
})

describe('heatmap helpers', () => {
  it('stores every frame on each point, with -1 for missing forecasts', () => {
    const data = heatmap(49, 3)
    const features = heatmapFeatures(data)
    expect(features.features).toHaveLength(3)
    const last = features.features[2]
    expect(last.geometry.coordinates).toEqual([-99, 34])
    expect(last.properties?.[frameProperty(0)]).toBe(2)
    expect(last.properties?.[frameProperty(1)]).toBe(-1) // null -> unknown, not 0 (Low)
    expect(Object.keys(features.features[0].properties ?? {})).toHaveLength(50) // i + r0..r48
  })

  it('builds frame-specific style expressions', () => {
    expect(heatmapColorExpression(12)).toEqual([
      'match',
      ['get', 'r12'],
      0,
      '#16a34a',
      1,
      '#eab308',
      2,
      '#f97316',
      3,
      '#dc2626',
      4,
      '#4c0519',
      UNKNOWN_COLOR,
    ])
    expect(heatmapOpacityExpression(3)).toEqual(['case', ['==', ['get', 'r3'], -1], 0.25, 0.5])
  })

  it('scales cell radius with zoom', () => {
    const expr = heatmapRadiusExpression(0.25, 0) as unknown as [string, unknown, unknown, number, number, number, number]
    expect(expr[0]).toBe('interpolate')
    expect(expr[6] / expr[4]).toBeCloseTo(2 ** 16)
  })

  it('reports frame coverage', () => {
    const data = heatmap(49, 3)
    expect(frameCoverage(data, 0)).toBe(1)
    expect(frameCoverage(data, 1)).toBeCloseTo(2 / 3)
  })
})

describe('checkpoint detail rows', () => {
  it('shows values, units and load-rule adjustments', () => {
    const rows = checkpointRows(
      checkpoint({
        mile: 125,
        segment_start_mile: 112.5,
        segment_end_mile: 137.5,
        weather: { wind_mph: 46.2, wind_gust_mph: 61, rain_in_per_hr: 0.12, snow_in_per_hr: 0 },
        risk: {
          overall: 'no_travel',
          wind: 'no_travel',
          wind_before_load_rule: 'severe',
          rain: 'moderate',
          snow: 'low',
          load_rule_applied: true,
        },
        hazards: ['wind'],
      }),
    )
    const byLabel = Object.fromEntries(rows.map((r) => [r.label, r.value]))
    expect(byLabel.Mile).toBe('125.0 (covers mi 112.5–137.5)')
    expect(byLabel.Wind).toBe('46 mph, gusts 61 mph · Severe → No Travel (load rule)')
    expect(byLabel.Rain).toBe('0.12 in/hr · Moderate')
    expect(byLabel.Snow).toBe('0.00 in/hr · Low')
    expect(byLabel.Risk).toBe('No Travel (Wind)')
  })

  it('says unknown, not low, when the forecast is missing', () => {
    const rows = checkpointRows(UNAVAILABLE_CHECKPOINT)
    expect(rows.find((r) => r.label === 'Risk')?.value).toBe('Unknown: forecast unavailable')
    expect(rows.some((r) => r.label === 'Wind')).toBe(false)
  })
})
