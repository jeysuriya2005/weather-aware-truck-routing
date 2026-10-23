// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { heatmap, plan, route, summary } from '../test/fixtures'
import { HeatmapControl } from './HeatmapControl'
import { RecommendationPanel } from './RecommendationPanel'
import { RouteList } from './RouteList'

afterEach(cleanup)

describe('HeatmapControl', () => {
  it('offers 0-48 h relative to departure and reports slider changes', () => {
    const onFrameChange = vi.fn()
    render(
      <HeatmapControl heatmap={heatmap()} frame={0} onFrameChange={onFrameChange} visible onVisibleChange={() => {}} />,
    )
    const slider = screen.getByRole('slider', { name: 'Forecast hours after departure' })
    expect(slider).toHaveProperty('min', '0')
    expect(slider).toHaveProperty('max', '48')
    expect(screen.getByText(/Departure \+0 h/)).toBeTruthy()

    fireEvent.change(slider, { target: { value: '12' } })
    expect(onFrameChange).toHaveBeenCalledWith(12)
  })

  it('labels the selected frame and warns about missing forecast cells', () => {
    render(
      <HeatmapControl heatmap={heatmap()} frame={1} onFrameChange={() => {}} visible onVisibleChange={() => {}} />,
    )
    expect(screen.getByText(/Departure \+1 h/)).toBeTruthy()
    expect(screen.getByText(/33% of the corridor has no forecast for this hour/)).toBeTruthy()
  })

  it('shows a legend with a separate "No forecast" entry', () => {
    render(
      <HeatmapControl heatmap={heatmap()} frame={0} onFrameChange={() => {}} visible onVisibleChange={() => {}} />,
    )
    const legend = screen.getByRole('list', { name: 'Risk level legend' })
    const items = within(legend).getAllByRole('listitem').map((li) => li.textContent)
    expect(items).toEqual(['Low', 'Moderate', 'High', 'Severe', 'No Travel', 'No forecast'])
  })

  it('toggles the overlay and disables the slider when hidden', () => {
    const onVisibleChange = vi.fn()
    const { rerender } = render(
      <HeatmapControl heatmap={heatmap()} frame={0} onFrameChange={() => {}} visible onVisibleChange={onVisibleChange} />,
    )
    fireEvent.click(screen.getByRole('checkbox', { name: 'Weather risk overlay' }))
    expect(onVisibleChange).toHaveBeenCalledWith(false)
    rerender(
      <HeatmapControl heatmap={heatmap()} frame={0} onFrameChange={() => {}} visible={false} onVisibleChange={onVisibleChange} />,
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
    expect(within(second).getByText('12.0 mi')).toBeTruthy()
    expect(within(second).getByText('0.73 / 4')).toBeTruthy()
  })

  it('shows unknown miles as unknown risk, not low', () => {
    const data = plan({
      routes: [route(0, { risk_summary: summary({ unknown_miles: 40, coverage_complete: false }) })],
    })
    render(<RouteList plan={data} selectedRouteId={null} onSelect={() => {}} />)
    expect(screen.getByText('40.0 mi (unknown risk, not low)')).toBeTruthy()
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
