// Regression and consistency tests added during the QA audit.
import { describe, expect, it } from 'vitest'
import { ApiError } from '../api/client'
import { UNAVAILABLE_CHECKPOINT, checkpoint, heatmap, route, summary } from '../test/fixtures'
import { describeApiError, flattenFieldErrors } from './apiErrors'
import { departureBounds, departureProblem } from './datetime'
import { cellForecast, frameForForecastHour, frameLabel } from './heatmap'
import { formatShare, routeInsights } from './insights'
import { RISK_LEVELS, UNKNOWN_INK, UNKNOWN_TINT, riskTint } from './risk'

describe('API error descriptions', () => {
  it('flattens nested DRF field errors with readable labels', () => {
    expect(
      flattenFieldErrors({
        origin: { lat: ['Ensure this value is less than or equal to 90.'] },
        departure_time: ['Must include a UTC offset.'],
        non_field_errors: ['Destination must differ from origin.'],
      }),
    ).toEqual([
      'Origin latitude: Ensure this value is less than or equal to 90.',
      'Departure: Must include a UTC offset.',
      'Destination must differ from origin.',
    ])
  })

  it('uses field reasons for validation errors and the server message otherwise', () => {
    expect(
      describeApiError(new ApiError(400, 'invalid_request', 'Some fields are invalid.', { load_weight_lb: ['Too big.'] })),
    ).toEqual({ title: 'Please check the trip details', details: ['Load weight: Too big.'] })
    expect(describeApiError(new ApiError(422, 'no_route_found', 'No drivable route was found between these locations.')))
      .toEqual({ title: 'No drivable route found', details: ['No drivable route was found between these locations.'] })
    expect(describeApiError(new Error('boom')).title).toBe('Something went wrong')
  })
})

describe('departure window mirrors the backend (15 min past .. 13 days ahead)', () => {
  const now = new Date('2026-10-24T12:00:00Z')

  it.each([
    ['2026-10-24T11:45:00Z', null],
    ['2026-10-24T11:44:00Z', 'Departure cannot be in the past.'],
    ['2026-11-06T12:00:00Z', null],
    ['2026-11-06T12:01:00Z', 'Departure must be within 13 days so forecasts cover the trip and the 48-hour outlook.'],
  ])('%s -> %s', (iso, expected) => {
    expect(departureProblem(iso, now)).toBe(expected)
  })

  it('exposes the same range as datetime-local min/max', () => {
    const { min, max } = departureBounds(now)
    expect(new Date(min).getTime()).toBeGreaterThanOrEqual(now.getTime() - 15 * 60_000)
    expect(new Date(max).getTime()).toBeLessThanOrEqual(now.getTime() + 13 * 86_400_000)
  })
})

describe('heatmap frame labels', () => {
  it('separates departure + N h from the forecast hour used', () => {
    const data = heatmap()
    data.frame_times = data.frame_times.map((_, f) => new Date(Date.UTC(2026, 9, 25, 14 + f)).toISOString())
    const label = frameLabel(data, '2026-10-25T13:20:00Z', 12)
    expect(label.offsetHours).toBe(12)
    expect(label.moment).toBe('2026-10-26T01:20:00.000Z')
    expect(label.forecastHour).toBe('2026-10-26T02:00:00.000Z')
  })
})

describe('route insights use only real checkpoint data', () => {
  it('finds peaks with their checkpoint and ignores unavailable checkpoints', () => {
    const insights = routeInsights(
      route(0, {
        checkpoints: [
          checkpoint({ index: 0, weather: { wind_mph: 12, wind_gust_mph: null, rain_in_per_hr: 0.02, snow_in_per_hr: 0 } }),
          checkpoint({ index: 1, mile: 25, weather: { wind_mph: 30, wind_gust_mph: 44, rain_in_per_hr: 0, snow_in_per_hr: 0.6 } }),
          UNAVAILABLE_CHECKPOINT,
        ],
      }),
    )
    expect(insights.peakWind?.value).toBe(30)
    expect(insights.peakWind?.checkpoint.mile).toBe(25)
    expect(insights.peakGust?.value).toBe(44)
    expect(insights.peakRain?.value).toBe(0.02)
    expect(insights.peakSnow?.value).toBe(0.6)
    expect([insights.checkpointsWithForecast, insights.checkpointsTotal]).toEqual([2, 3])
  })

  it('returns nulls, not zeros, when no forecast exists', () => {
    const insights = routeInsights(route(0, { checkpoints: [UNAVAILABLE_CHECKPOINT], risk_summary: null }))
    expect(insights.peakWind).toBeNull()
    expect(insights.worst).toBeNull()
    expect(insights.highOrWorseMiles).toBeNull()
    expect(insights.distribution).toEqual([{ code: 'unknown', miles: 12.5, share: 1 }])
  })

  it('builds the distribution from the API summary, including unknown miles', () => {
    const insights = routeInsights(
      route(0, {
        risk_summary: summary({
          total_miles: 100,
          miles_by_level: { low: 50, moderate: 0, high: 20, severe: 10, no_travel: 0 },
          severe_or_worse_miles: 10,
          unknown_miles: 20,
        }),
      }),
    )
    expect(insights.distribution.map((s) => [s.code, s.share])).toEqual([
      ['low', 0.5],
      ['high', 0.2],
      ['severe', 0.1],
      ['unknown', 0.2],
    ])
    expect(insights.highOrWorseMiles).toBe(30)
  })

  it.each([
    [0, '0%'],
    [0.004, '<1%'],
    [0.5, '50%'],
    [0.996, '>99%'],
    [1, '100%'],
  ])('formatShare(%s) = %s', (share, text) => {
    expect(formatShare(share)).toBe(text)
  })
})

describe('badge colours are accessible', () => {
  const luminance = (hex: string) => {
    const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
      .map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b
  }
  const contrast = (a: string, b: string) => {
    const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
    return (hi + 0.05) / (lo + 0.05)
  }

  it.each([...RISK_LEVELS.map((l) => [l.label, l.ink, l.tint]), ['No forecast', UNKNOWN_INK, UNKNOWN_TINT]])(
    '%s badge text meets WCAG AA (4.5:1)',
    (_, ink, tint) => {
      expect(contrast(ink, tint)).toBeGreaterThanOrEqual(4.5)
    },
  )

  it('unknown never uses the Low style', () => {
    expect(riskTint(null)).not.toEqual(riskTint('low'))
  })
})

describe('shading vs checkpoint times (regression: dot "Low" vs shading "Severe" at a different hour)', () => {
  it('finds the overlay frame that uses the same forecast hour as a checkpoint ETA', () => {
    const data = heatmap()
    expect(frameForForecastHour(data, data.frame_times[7])).toBe(7)
    expect(frameForForecastHour(data, '2026-10-25T13:00:00Z')).toBe(0)
    expect(frameForForecastHour(data, '2026-10-30T00:00:00Z')).toBeNull() // beyond 48 h
  })

  it('reads one corridor cell at one frame', () => {
    const data = heatmap(49, 3)
    expect(cellForecast(data, 1, 0)).toEqual({ index: 1, lat: 33, lon: -98, risk: 1, windMph: 10, rainInPerHr: 0, snowInPerHr: 0 })
    expect(cellForecast(data, 2, 1).risk).toBeNull() // missing stays missing
  })
})
