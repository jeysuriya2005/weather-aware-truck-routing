/**
 * Browser QA with mocked API responses (deterministic, no external calls for app data;
 * base-map tiles still load from OpenFreeMap).
 */
import { expect, test } from '@playwright/test'
import { formatDuration, formatMiles } from '../src/lib/units.ts'
import { DEPARTURE, planFixture } from './fixtures.ts'
import { fillTrip, formatInPage, mockApi, pickPlace, planTrip, suggestions, waitForMap, watchProblems } from './helpers.ts'

let problems: string[] = []

test.beforeEach(async ({ page }) => {
  problems = watchProblems(page)
})

test.afterEach(() => {
  expect(problems, 'browser console/page errors').toEqual([])
})

test('initial empty state', async ({ page }) => {
  await mockApi(page)
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Weather-Aware Truck Routing' })).toBeVisible()
  await expect(page.getByText('API: online')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Plan a trip to compare routes' })).toBeVisible()
  await expect(page.locator('.maplibregl-canvas')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Generate Routes' })).toBeEnabled()
})

test('geocoding suggestions: typing, keyboard selection and no-match state', async ({ page }) => {
  await mockApi(page)
  await page.goto('/')
  const origin = page.getByLabel('Origin', { exact: true })
  await origin.fill('Dal')
  await expect(suggestions(page)).toHaveText([/Dallas, TX/, /Dalhart, TX/])
  await origin.press('ArrowDown')
  await origin.press('Enter')
  await expect(origin).toHaveValue('Dalhart, TX')
  await pickPlace(page, 'Destination', 'Denver')
  await expect(page.getByLabel('Destination', { exact: true })).toHaveValue('Denver, CO')
  await page.getByLabel('Destination', { exact: true }).fill('Zzq')
  await expect(page.getByText('No matching locations')).toBeVisible()
})

test('client-side validation messages', async ({ page }) => {
  const requests = await mockApi(page)
  await page.goto('/')
  await page.getByRole('button', { name: 'Generate Routes' }).click()
  await expect(page.getByRole('alert')).toHaveText('Choose an origin from the suggestions.')

  await fillTrip(page, '250000')
  await page.getByRole('button', { name: 'Generate Routes' }).click()
  await expect(page.getByRole('alert')).toHaveText('Enter a load weight between 0 and 200,000 lb.')

  await page.getByLabel('Load weight (lb)').fill('38000')
  const far = await page.evaluate(() => {
    const d = new Date(Date.now() + 20 * 86_400_000)
    const p = (n: number) => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T09:00`
  })
  await page.getByLabel('Departure (your local time)').fill(far)
  await page.getByRole('button', { name: 'Generate Routes' }).click()
  await expect(page.getByRole('alert')).toContainText('within 13 days')
  expect(requests).toHaveLength(0)
})

test('server validation errors show the field reason (regression)', async ({ page }) => {
  await mockApi(page, {
    planStatus: 400,
    planBody: {
      error: {
        code: 'invalid_request',
        message: 'Some fields are invalid.',
        fields: { departure_time: ['Departure time must be within 13 days so forecasts cover the trip.'] },
      },
    },
  })
  await page.goto('/')
  await fillTrip(page)
  await page.getByRole('button', { name: 'Generate Routes' }).click()
  const alert = page.getByRole('alert')
  await expect(alert).toContainText('Please check the trip details')
  await expect(alert).toContainText('Departure: Departure time must be within 13 days so forecasts cover the trip.')
})

for (const [name, mock, title, detail] of [
  ['no route', { planStatus: 422, planBody: { error: { code: 'no_route_found', message: 'No drivable route was found between these locations.' } } },
    'No drivable route found', 'No drivable route was found between these locations.'],
  ['routing not configured', { planStatus: 503, planBody: { error: { code: 'provider_not_configured', message: 'The routing provider is not configured on the server.' } } },
    'Routing is not configured on the server', 'The routing provider is not configured on the server.'],
  ['network failure', { abortPlan: true }, 'Cannot reach the server', 'Could not reach the server. Check that the API is running.'],
] as const) {
  test(`error state: ${name}`, async ({ page }) => {
    await mockApi(page, mock)
    await page.goto('/')
    await fillTrip(page)
    await page.getByRole('button', { name: 'Generate Routes' }).click()
    await expect(page.getByRole('alert')).toContainText(title)
    await expect(page.getByRole('alert')).toContainText(detail)
    await expect(page.getByRole('button', { name: 'Generate Routes' })).toBeEnabled()
  })
}

test('loading state, then route cards and recommendation match the API data', async ({ page }) => {
  const plan = planFixture()
  // Long enough that the loading state is still visible on a slow (software-WebGL) runner.
  await mockApi(page, { plan, planDelayMs: 4000 })
  await page.goto('/')
  await fillTrip(page)
  await page.getByRole('button', { name: 'Generate Routes' }).click()
  await expect(page.getByRole('button', { name: 'Generating routes…' })).toBeDisabled()
  await expect(page.getByRole('status')).toContainText('Calculating truck routes and checkpoint forecasts')
  await expect(page.getByRole('region', { name: 'Recommendation' })).toBeVisible()
  await waitForMap(page)

  const recommended = plan.routes.find((r) => r.id === plan.recommendation.route_id)!
  await expect(page.getByRole('region', { name: 'Recommendation' }).getByRole('heading', { level: 2 }))
    .toHaveText(`Recommended route: ${recommended.label}`)

  const cards = page.getByRole('region', { name: 'Route options' }).getByRole('button')
  await expect(cards).toHaveCount(plan.routes.length)
  for (const [i, route] of plan.routes.entries()) {
    const card = cards.nth(i)
    const metric = (label: string) => card.locator('dt', { hasText: label }).locator('xpath=following-sibling::dd[1]')
    await expect(card).toContainText(route.label)
    await expect(metric('Distance')).toHaveText(formatMiles(route.distance_miles))
    await expect(metric('Drive time')).toHaveText(formatDuration(route.duration_seconds))
    await expect(metric('ETA')).toHaveText(await formatInPage(page, route.arrival_time))
    const s = route.risk_summary!
    await expect(metric('Avg risk')).toHaveText(`${s.average_risk!.toFixed(2)} / 4`)
    await expect(metric('High')).toHaveText(formatMiles(s.miles_by_level.high))
    await expect(metric('Severe+')).toHaveText(formatMiles(s.severe_or_worse_miles))
    await expect(card.getByText(`#${route.rank}`)).toBeVisible()
    if (s.has_no_travel) await expect(card.getByText('Unsafe: No Travel')).toBeVisible()
    if (route.recommended) await expect(card.getByText('Recommended')).toBeVisible()
    if (s.unknown_miles > 0) await expect(card.getByText(/unknown risk, not low/)).toBeVisible()
  }
  await expect(page.getByText(`${recommended.label} checkpoints (${recommended.checkpoints.length})`)).toBeVisible()
})

test('route switching, checkpoint list and map popup agree', async ({ page }) => {
  const plan = planFixture()
  await mockApi(page, { plan })
  await page.goto('/')
  await planTrip(page)

  const routeA = plan.routes[0]
  await page.getByRole('region', { name: 'Route options' }).getByRole('button', { name: /Route A/ }).click()
  await expect(page.getByText(`Route A checkpoints (${routeA.checkpoints.length})`)).toBeVisible()

  // A No Travel checkpoint (index 8) produced by the load rule.
  const cp = routeA.checkpoints[8]
  await page.locator('.checkpoint-row').nth(8).click()
  const popup = page.locator('.maplibregl-popup')
  await expect(popup).toBeVisible()
  await expect(popup).toContainText(`Route A · checkpoint 9: No Travel`)
  const detail = page.locator('.checkpoint-detail')
  for (const text of [
    `${cp.mile.toFixed(1)} (covers mi ${cp.segment_start_mile.toFixed(1)}–${cp.segment_end_mile.toFixed(1)})`,
    await formatInPage(page, cp.eta),
    '47 mph, gusts 63 mph · Severe → No Travel (load rule)',
    'Load rule: 38,000 lb with 47 mph wind raises wind risk from Severe to No Travel.',
  ]) {
    await expect(popup).toContainText(text)
    await expect(detail).toContainText(text)
  }

  // Switching routes closes the stale popup and swaps the checkpoint list.
  await page.getByRole('region', { name: 'Route options' }).getByRole('button', { name: /Route B/ }).click()
  await expect(popup).toHaveCount(0)
  await expect(page.getByText(`Route B checkpoints (${plan.routes[1].checkpoints.length})`)).toBeVisible()
})

test('unavailable checkpoint is shown as unknown, not Low', async ({ page }) => {
  const plan = planFixture()
  await mockApi(page, { plan })
  await page.goto('/')
  await planTrip(page)
  await page.getByRole('region', { name: 'Route options' }).getByRole('button', { name: /Route C/ }).click()
  await page.locator('.checkpoint-row').nth(5).click()
  await expect(page.locator('.checkpoint-row').nth(5)).toContainText('No forecast')
  await expect(page.locator('.checkpoint-detail')).toContainText('Unknown: forecast unavailable')
  await expect(page.locator('.maplibregl-popup')).toContainText('risk is unknown, not low')
})

test('heatmap slider: departure-relative label, forecast hour, toggle', async ({ page }) => {
  const plan = planFixture()
  await mockApi(page, { plan })
  await page.goto('/')
  await planTrip(page)
  const control = page.getByRole('region', { name: 'Weather risk overlay' })
  const slider = control.getByRole('slider', { name: 'Forecast hours after departure' })
  await expect(slider).toHaveAttribute('max', '48')

  await slider.fill('12')
  await expect(control).toContainText('Shading at departure +12 h')
  const moment = new Date(Date.parse(DEPARTURE) + 12 * 3_600_000).toISOString()
  await expect(control).toContainText(await formatInPage(page, moment))
  // Frame 12 has missing cells in the fixture -> explicit missing-data message.
  await expect(control).toContainText(/of the corridor has no forecast for this hour \(shown grey, not low risk\)/)

  await control.getByRole('checkbox', { name: 'Weather risk overlay' }).uncheck()
  await expect(slider).toBeDisabled()
  await expect(control.getByRole('list', { name: 'Risk level legend' }).getByRole('listitem'))
    .toHaveText(['Low', 'Moderate', 'High', 'Severe', 'No Travel', 'No forecast'])
})

test('weather unavailable: no recommendation, no Low badges or zero metrics', async ({ page }) => {
  await mockApi(page, { plan: planFixture({ weatherUnavailable: true }) })
  await page.goto('/')
  await planTrip(page)
  await expect(page.getByRole('region', { name: 'Recommendation' }).getByRole('heading', { level: 2 })).toHaveText('No recommendation')
  const options = page.getByRole('region', { name: 'Route options' })
  await expect(options.getByText('Weather risk unknown: forecast unavailable.')).toHaveCount(3)
  await expect(options.getByText(/Worst: Low/)).toHaveCount(0)
  await expect(options.getByText('Avg risk')).toHaveCount(0)
  await expect(page.getByText('Forecasts unavailable · 0/')).toBeVisible()
  await expect(page.getByRole('region', { name: 'Weather risk overlay' })).toContainText('Grey means no data, not low risk')
})

test('repeated submissions replace results and send the current inputs', async ({ page }) => {
  let call = 0
  const requests = await mockApi(page, {
    plan: () => planFixture({ label: ++call === 1 ? 'Denver, CO' : 'Second plan' }),
    planDelayMs: 300,
  })
  await page.goto('/')
  await planTrip(page)
  await page.getByLabel('Weather checkpoints').selectOption('10')
  await page.getByRole('button', { name: 'Generate Routes' }).click()
  await expect(page.getByRole('button', { name: 'Generate Routes' })).toBeEnabled()
  expect(requests).toHaveLength(2)
  expect((requests[1] as { checkpoint_interval_miles: number }).checkpoint_interval_miles).toBe(10)
  expect((requests[0] as { load_weight_lb: number }).load_weight_lb).toBe(38000)
  await expect(page.getByRole('region', { name: 'Route options' }).getByRole('button')).toHaveCount(3)
})

test('map zoom controls and route selection from the map panel', async ({ page }) => {
  await mockApi(page)
  await page.goto('/')
  await planTrip(page)
  const scale = page.locator('.maplibregl-ctrl-scale')
  await page.waitForTimeout(800) // fitBounds animation
  const before = await scale.textContent()
  await page.getByRole('button', { name: 'Zoom in' }).click()
  await page.getByRole('button', { name: 'Zoom in' }).click()
  await expect(scale).not.toHaveText(before ?? '')
  // Drag-pan the map; must not throw or change the selection.
  const box = (await page.locator('.maplibregl-canvas').boundingBox())!
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 3)
  await page.mouse.down()
  await page.mouse.move(box.x + box.width / 2 + 120, box.y + box.height / 3 + 60, { steps: 8 })
  await page.mouse.up()
  await expect(page.locator('.route-card.is-selected')).toHaveCount(1)
})

test('checkpoint vs shading time: explanation and "show shading at this ETA" (regression)', async ({ page }) => {
  const plan = planFixture()
  await mockApi(page, { plan })
  await page.goto('/')
  await planTrip(page)
  const slider = page.getByRole('slider', { name: 'Forecast hours after departure' })
  await slider.fill('35')
  await expect(page.getByRole('region', { name: 'Weather risk overlay' })).toContainText('Shading at departure +35 h')

  const route = plan.routes.find((r) => r.id === plan.recommendation.route_id)!
  const cp = route.checkpoints[6]
  const etaFrame = plan.heatmap.frame_times.findIndex((t) => Date.parse(t) === Date.parse(cp.forecast_time))
  expect(etaFrame).toBeGreaterThanOrEqual(0)

  await page.locator('.checkpoint-row').nth(6).click()
  const detail = page.locator('.checkpoint-detail')
  await expect(detail).toContainText(`Map shading shows departure +35 h; the truck reaches this checkpoint at +${etaFrame} h`)
  await detail.getByRole('button', { name: `Show shading at this ETA (+${etaFrame} h)` }).click()
  await expect(slider).toHaveValue(String(etaFrame))
  await expect(detail).toContainText(`Map shading shows this checkpoint's forecast hour (departure +${etaFrame} h)`)

  // The same action from the map popup.
  await slider.fill('40')
  await page.locator('.maplibregl-popup').getByRole('button', { name: `Show shading at this ETA (+${etaFrame} h)` }).click()
  await expect(slider).toHaveValue(String(etaFrame))
})
