import { describe, expect, it } from 'vitest'
import { formatDuration, formatMiles, formatPounds, metersToMiles } from './units'
import { defaultDeparture, localInputToIso, toLocalInputValue } from './datetime'

describe('metersToMiles', () => {
  it.each([
    [0, 0],
    [1609.344, 1],
    [40_233.6, 25],
    [1_419_953, 882.3179],
  ])('%d m -> %d mi', (meters, miles) => {
    expect(metersToMiles(meters)).toBeCloseTo(miles, 4)
  })
})

describe('formatMiles', () => {
  it.each([
    [0.04, '0.0 mi'],
    [24.96, '25.0 mi'],
    [882.31, '882 mi'],
    [1234.6, '1,235 mi'],
  ])('%d -> %s', (miles, expected) => {
    expect(formatMiles(miles)).toBe(expected)
  })
})

describe('formatDuration', () => {
  it.each([
    [0, '0 min'],
    [29, '0 min'],
    [30, '1 min'],
    [3599, '1 h'],
    [3600, '1 h'],
    [42_540, '11 h 49 min'],
    [51_060, '14 h 11 min'],
  ])('%d s -> %s', (seconds, expected) => {
    expect(formatDuration(seconds)).toBe(expected)
  })
})

describe('formatPounds', () => {
  it('uses thousands separators', () => {
    expect(formatPounds(38000)).toBe('38,000 lb')
  })
})

describe('datetime helpers', () => {
  it('round-trips a local input value through ISO', () => {
    const local = new Date(2026, 9, 25, 8, 30) // local time
    const iso = localInputToIso(toLocalInputValue(local))
    expect(iso).toBe(local.toISOString())
  })

  it.each(['', '2026-10-25', 'next tuesday', '2026-13-45T99:99'])('rejects %j', (value) => {
    expect(localInputToIso(value)).toBeNull()
  })

  it('defaults departure to the next quarter hour', () => {
    const result = defaultDeparture(new Date(2026, 9, 25, 8, 7, 42))
    expect([result.getHours(), result.getMinutes(), result.getSeconds()]).toEqual([8, 15, 0])
    const onBoundary = defaultDeparture(new Date(2026, 9, 25, 8, 15, 0))
    expect([onBoundary.getHours(), onBoundary.getMinutes()]).toEqual([8, 30])
    const rollover = defaultDeparture(new Date(2026, 9, 25, 23, 50))
    expect([rollover.getDate(), rollover.getHours(), rollover.getMinutes()]).toEqual([26, 0, 0])
  })
})
