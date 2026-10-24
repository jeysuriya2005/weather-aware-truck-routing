// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import { describeApiError } from '../lib/apiErrors'
import { UNAVAILABLE_CHECKPOINT, checkpoint, heatmap, plan, route, summary } from '../test/fixtures'
import { CheckpointList } from './CheckpointList'
import { ErrorNotice } from './ErrorNotice'
import { HeatmapControl } from './HeatmapControl'
import { RecommendationPanel } from './RecommendationPanel'
import { RouteInsights } from './RouteInsights'
import { RouteList } from './RouteList'

afterEach(cleanup)

// The fixture heatmap's frame 0 is 13:00 UTC; this departure is on the hour.
const DEPARTURE = '2026-10-25T13:00:00Z'

describe('HeatmapControl', () => {
  it('offers 0-48 h relative to departure and reports slider changes', () => {
    const onFrameChange = vi.fn()
    render(
      <HeatmapControl heatmap={heatmap()} departureTime={DEPARTURE} frame={0} onFrameChange={onFrameChange} visible onVisibleChange={() => {}} />,
    )
    const slider = screen.getByRole('slider', { name: 'Forecast hours after departure' })
    expect(slider).toHaveProperty('min', '0')
    expect(slider).toHaveProperty('max', '48')
    expect(screen.getByText(/Shading at departure \+0 h/)).toBeTruthy()

    fireEvent.change(slider, { target: { value: '12' } })
    expect(onFrameChange).toHaveBeenCalledWith(12)
  })

  it('labels the selected frame and warns about missing forecast cells', () => {
    render(
      <HeatmapControl heatmap={heatmap()} departureTime={DEPARTURE} frame={1} onFrameChange={() => {}} visible onVisibleChange={() => {}} />,
    )
    expect(screen.getByText(/Shading at departure \+1 h/)).toBeTruthy()
    expect(screen.getByText(/33% of the corridor has no forecast for this hour/)).toBeTruthy()
  })

  it('shows departure + N h, not the forecast hour, as the slider time (regression)', () => {
    // Departs 13:20 UTC: +0 h is 13:20, while the forecast record used is the 14:00 hour.
    const data = heatmap()
    data.frame_times = data.frame_times.map((_, f) => new Date(Date.UTC(2026, 9, 25, 14 + f)).toISOString())
    render(
      <HeatmapControl heatmap={data} departureTime="2026-10-25T13:20:00Z" frame={0} onFrameChange={() => {}} visible onVisibleChange={() => {}} />,
    )
    const time = screen.getByText(/Shading at departure \+0 h/).parentElement!.textContent!
    const departureText = new Date('2026-10-25T13:20:00Z').toLocaleString('en-US', {
      weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZoneName: 'short',
    })
    expect(time).toContain(departureText)
    const forecastText = new Date('2026-10-25T14:00:00Z').toLocaleString('en-US', { weekday: 'short', hour: 'numeric', minute: '2-digit' })
    expect(screen.getByText(new RegExp(`Forecast hour ending ${forecastText}`))).toBeTruthy()
  })

  it('never rounds a small missing share down to 0% (regression)', () => {
    const data = heatmap(49, 200)
    data.risk[0] = data.risk[0].map((v, i) => (i === 0 ? null : (v ?? 0)))
    render(
      <HeatmapControl heatmap={data} departureTime={DEPARTURE} frame={0} onFrameChange={() => {}} visible onVisibleChange={() => {}} />,
    )
    expect(screen.getByText(/<1% of the corridor has no forecast/)).toBeTruthy()
  })

  it('shows a legend with a separate "No forecast" entry', () => {
    render(
      <HeatmapControl heatmap={heatmap()} departureTime={DEPARTURE} frame={0} onFrameChange={() => {}} visible onVisibleChange={() => {}} />,
    )
    const legend = screen.getByRole('list', { name: 'Risk level legend' })
    const items = within(legend).getAllByRole('listitem').map((li) => li.textContent)
    expect(items).toEqual(['Low', 'Moderate', 'High', 'Severe', 'No Travel', 'No forecast'])
  })

  it('toggles the overlay and disables the slider when hidden', () => {
    const onVisibleChange = vi.fn()
    const { rerender } = render(
      <HeatmapControl heatmap={heatmap()} departureTime={DEPARTURE} frame={0} onFrameChange={() => {}} visible onVisibleChange={onVisibleChange} />,
    )
    fireEvent.click(screen.getByRole('checkbox', { name: 'Weather risk overlay' }))
    expect(onVisibleChange).toHaveBeenCalledWith(false)
    rerender(
      <HeatmapControl heatmap={heatmap()} departureTime={DEPARTURE} frame={0} onFrameChange={() => {}} visible={false} onVisibleChange={onVisibleChange} />,
    )
    expect(screen.getByRole('slider')).toHaveProperty('disabled', true)
  })
})

describe('RouteList risk display', () => {
  it('marks the recommended route and an unsafe No Travel route', () => {
    const data = plan({
      routes: [
        route(0),
        route(1, {
          recommended: false,
          risk_summary: summary({
            miles_by_level: { low: 80, moderate: 0, high: 5, severe: 3, no_travel: 12 },
            severe_or_worse_miles: 15,
            max_risk: 'no_travel',
            has_no_travel: true,
            average_risk: 0.73,
          }),
        }),
      ],
    })
    render(<RouteList plan={data} selectedRouteId={null} onSelect={() => {}} />)
    const [first, second] = screen.getAllByRole('button')
    expect(within(first).getByText('Recommended')).toBeTruthy()
    expect(within(second).getByText('Unsafe: No Travel')).toBeTruthy()
    expect(within(second).getByText('Worst: No Travel')).toBeTruthy()
    expect(within(second).getByText('No Travel 12.0 mi')).toBeTruthy()
    // Metrics shown on the card are the API's values.
    const metric = (label: string) => within(second).getByText(label).nextElementSibling?.textContent
    expect(metric('Avg risk')).toBe('0.73 / 4')
    expect(metric('High')).toBe('5.0 mi')
    expect(metric('Severe+')).toBe('15.0 mi')
    expect(metric('Coverage')).toBe('100%')
  })

  it('explains when a long trip reads forecasts from a coarser grid', () => {
    const base = plan()
    const data = plan({ weather_risk: { ...base.weather_risk, forecast_grid_degrees: 0.15, forecast_locations: 497 } })
    render(<RouteList plan={data} selectedRouteId={null} onSelect={() => {}} />)
    expect(screen.getByText(/checkpoints are still every 25 mi, but forecasts are read from a 0.15° grid \(about 17 km\)/)).toBeTruthy()
  })

  it('shows no grid notice on normal trips', () => {
    const base = plan()
    render(<RouteList plan={plan({ weather_risk: { ...base.weather_risk, forecast_grid_degrees: 0.05 } })} selectedRouteId={null} onSelect={() => {}} />)
    expect(screen.queryByText(/forecasts are read from a/)).toBeNull()
  })

  it('shows unknown miles as unknown risk, not low', () => {
    const data = plan({
      routes: [route(0, { risk_summary: summary({ unknown_miles: 40, coverage_complete: false }) })],
    })
    render(<RouteList plan={data} selectedRouteId={null} onSelect={() => {}} />)
    expect(screen.getByText('No forecast: 40.0 mi (unknown risk, not low)')).toBeTruthy()
  })

  it('shows "weather risk unknown" when no forecast is available', () => {
    const data = plan({
      routes: [route(0, { risk_summary: null, recommended: false, rank: null })],
      weather_risk: { ...plan().weather_risk, status: 'unavailable', message: 'The weather provider is down.' },
    })
    render(<RouteList plan={data} selectedRouteId={null} onSelect={() => {}} />)
    expect(screen.getByText('Weather risk unknown: forecast unavailable.')).toBeTruthy()
    expect(screen.getByRole('alert').textContent).toBe('The weather provider is down.')
    expect(screen.queryByText('Recommended')).toBeNull()
    // No misleading zeros or Low badges when risk is unknown.
    expect(screen.queryByText('Avg risk')).toBeNull()
    expect(screen.queryByText(/Worst: Low/)).toBeNull()
  })
})

describe('RouteInsights', () => {
  it('summarises the real checkpoint weather of the selected route', () => {
    const r = route(0, {
      checkpoints: [
        checkpoint({ index: 0, mile: 0 }),
        checkpoint({
          index: 1,
          mile: 25,
          weather: { wind_mph: 41.6, wind_gust_mph: 58, rain_in_per_hr: 0.31, snow_in_per_hr: 0 },
          risk: { overall: 'severe', wind: 'severe', wind_before_load_rule: 'high', rain: 'high', snow: 'low', load_rule_applied: true },
          hazards: ['wind'],
        }),
        UNAVAILABLE_CHECKPOINT,
      ],
      risk_summary: summary({
        miles_by_level: { low: 12.5, moderate: 0, high: 0, severe: 25, no_travel: 0 },
        severe_or_worse_miles: 25,
        unknown_miles: 12.5,
        max_risk: 'severe',
        total_miles: 50,
        coverage_complete: false,
      }),
    })
    render(<RouteInsights route={r} selectedCheckpoint={null} onSelectCheckpoint={() => {}} />)
    const tile = (label: string) => screen.getByText(label).closest('.kpi')!.textContent
    expect(tile('Peak wind')).toContain('42 mph')
    expect(tile('Peak wind')).toContain('mi 25')
    expect(tile('Peak wind')).toContain('gusts to 58 mph')
    expect(tile('Peak rain')).toContain('0.31 in/hr')
    expect(tile('Worst risk')).toContain('Severe')
    expect(tile('High or worse')).toContain('25.0 mi')
    expect(tile('Forecast coverage')).toContain('67%')
    expect(tile('Forecast coverage')).toContain('2 of 3 checkpoints')
    expect(screen.getByRole('img', { name: /No forecast 12\.5 mi/ })).toBeTruthy()
  })

  it('shows "No forecast" instead of zeros when nothing is known', () => {
    const r = route(0, { checkpoints: [UNAVAILABLE_CHECKPOINT], risk_summary: null })
    render(<RouteInsights route={r} selectedCheckpoint={null} onSelectCheckpoint={() => {}} />)
    expect(screen.getByText('Peak wind').closest('.kpi')!.textContent).toContain('No forecast')
    expect(screen.getByText('High or worse').closest('.kpi')!.textContent).toContain('Unknown')
    expect(screen.queryByText('0 mph')).toBeNull()
  })
})

describe('ErrorNotice', () => {
  it('shows server field reasons instead of a generic message (regression)', () => {
    const error = describeApiError(
      new ApiError(400, 'invalid_request', 'Some fields are invalid.', {
        departure_time: ['Departure time must be within 13 days so forecasts cover the trip.'],
      }),
    )
    render(<ErrorNotice error={error} />)
    expect(screen.getByRole('alert').textContent).toContain('Please check the trip details')
    expect(screen.getByRole('alert').textContent).toContain(
      'Departure: Departure time must be within 13 days so forecasts cover the trip.',
    )
    expect(screen.getByRole('alert').textContent).not.toContain('Some fields are invalid.')
  })
})

describe('RecommendationPanel', () => {
  it('explains the recommendation and lists hazards', () => {
    const routes = [
      route(0, {
        hazard_stretches: [
          {
            level: 'severe',
            hazards: ['snow'],
            start_mile: 112.5,
            end_mile: 162.5,
            first_eta: '2026-10-25T16:00:00+00:00',
            last_eta: '2026-10-25T17:00:00+00:00',
            first_index: 5,
            last_index: 6,
          },
        ],
      }),
    ]
    render(<RecommendationPanel recommendation={plan({ routes }).recommendation} routes={routes} />)
    expect(screen.getByRole('heading', { level: 2 }).textContent).toBe('Recommended route: Route A')
    expect(screen.getByText(/fastest/)).toBeTruthy()
    expect(screen.getByText(/mi 113–163/)).toBeTruthy()
  })

  it('states clearly when no route is fully safe', () => {
    const data = plan()
    const recommendation = {
      ...data.recommendation,
      status: 'no_safe_route' as const,
      explanation: 'No route is fully safe: every option has No Travel conditions.',
      warnings: ['Every route option includes No Travel conditions. Consider delaying departure.'],
    }
    render(<RecommendationPanel recommendation={recommendation} routes={data.routes} />)
    expect(screen.getByRole('heading', { level: 2 }).textContent).toBe('No fully safe route (least exposure: Route A)')
    expect(screen.getByRole('alert').textContent).toContain('Consider delaying departure')
  })

  it('does not recommend anything when weather is unavailable', () => {
    const data = plan()
    const recommendation = {
      ...data.recommendation,
      status: 'unavailable' as const,
      route_id: null,
      route_label: null,
      explanation: 'Route risk cannot be assessed; no route is recommended.',
    }
    render(<RecommendationPanel recommendation={recommendation} routes={data.routes} />)
    expect(screen.getByRole('heading', { level: 2 }).textContent).toBe('No recommendation')
  })
})

describe('CheckpointList overlay relation', () => {
  const data = heatmap()
  const cp = checkpoint({ index: 0, forecast_time: data.frame_times[7] })
  const r = route(0, { checkpoints: [cp] })

  it('explains a different shading hour and syncs it on request', () => {
    const onShowFrame = vi.fn()
    render(<CheckpointList route={r} selectedIndex={0} onSelect={() => {}} overlayFrame={35} heatmap={data} onShowFrame={onShowFrame} />)
    expect(screen.getByText(/Map shading shows departure \+35 h; the truck reaches this checkpoint at \+7 h/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Show shading at this ETA (+7 h)' }))
    expect(onShowFrame).toHaveBeenCalledWith(7)
  })

  it('confirms when shading and checkpoint show the same hour', () => {
    render(<CheckpointList route={r} selectedIndex={0} onSelect={() => {}} overlayFrame={7} heatmap={data} />)
    expect(screen.getByText(/Map shading shows this checkpoint's forecast hour \(departure \+7 h\)/)).toBeTruthy()
  })
})
