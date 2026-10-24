/**
 * LIVE end-to-end journey: real Django backend (via the Vite proxy to :8000),
 * real TomTom routing/geocoding and real Open-Meteo forecasts. Opt-in:
 *     E2E_LIVE=1 npx playwright test --project=live
 * Makes ~3 geocode calls and 1 trip plan. Every displayed value checked here is
 * compared with the actual API response captured from the same request.
 */
import { expect, test } from '@playwright/test'
import type { TripPlanResponse } from '../src/api/types.ts'
import { formatAverageRisk } from '../src/lib/risk.ts'
import { formatDuration, formatMiles } from '../src/lib/units.ts'
import { formatInPage, suggestions, waitForMap, watchProblems } from './helpers.ts'

test.skip(!process.env.E2E_LIVE, 'set E2E_LIVE=1 to run against the real backend and providers')

test('live journey: Denver -> Salt Lake City, UI matches API', async ({ page }) => {
  const problems = watchProblems(page)
  await page.goto('/')
  await expect(page.getByText('API: online')).toBeVisible({ timeout: 15_000 })

  for (const [label, text] of [['Origin', 'Denver, CO'], ['Destination', 'Salt Lake City, UT']] as const) {
    await page.getByLabel(label, { exact: true }).fill(text)
    await suggestions(page).first().click({ timeout: 15_000 })
  }
  await page.getByLabel('Load weight (lb)').fill('42000')

  const [response] = await Promise.all([
    page.waitForResponse((r) => r.url().endsWith('/api/trips/plan/'), { timeout: 120_000 }),
    page.getByRole('button', { name: 'Generate Routes' }).click(),
  ])
  expect(response.status()).toBe(200)
  const plan = (await response.json()) as TripPlanResponse
  await expect(page.getByRole('region', { name: 'Recommendation' })).toBeVisible()
  await waitForMap(page)

  // Recommendation
  const rec = plan.recommendation
  const heading = page.getByRole('region', { name: 'Recommendation' }).getByRole('heading', { level: 2 })
  if (rec.status === 'recommended') await expect(heading).toHaveText(`Recommended route: ${rec.route_label}`)
  await expect(page.getByRole('region', { name: 'Recommendation' })).toContainText(rec.explanation)

  // Route cards vs API
  const cards = page.getByRole('region', { name: 'Route options' }).getByRole('button')
  await expect(cards).toHaveCount(plan.routes.length)
  for (const [i, route] of plan.routes.entries()) {
    const card = cards.nth(i)
    const metric = (label: string) => card.locator('dt', { hasText: label }).locator('xpath=following-sibling::dd[1]')
    await expect(metric('Distance')).toHaveText(formatMiles(route.distance_miles))
    await expect(metric('Drive time')).toHaveText(formatDuration(route.duration_seconds))
    await expect(metric('ETA')).toHaveText(await formatInPage(page, route.arrival_time))
    if (route.risk_summary) {
      await expect(metric('Avg risk')).toHaveText(formatAverageRisk(route.risk_summary.average_risk))
      await expect(metric('High')).toHaveText(formatMiles(route.risk_summary.miles_by_level.high))
      await expect(metric('Severe+')).toHaveText(formatMiles(route.risk_summary.severe_or_worse_miles))
    }
  }

  // Checkpoint list + popup vs API for the selected (recommended) route
  const selected = plan.routes.find((r) => r.id === (rec.route_id ?? plan.routes[0].id))!
  await expect(page.getByText(`${selected.label} checkpoints (${selected.checkpoints.length})`)).toBeVisible()
  const cp = selected.checkpoints[Math.min(5, selected.checkpoints.length - 1)]
  await page.locator('.checkpoint-row').nth(cp.index).click()
  const popup = page.locator('.maplibregl-popup')
  await expect(popup).toContainText(await formatInPage(page, cp.eta))
  await expect(popup).toContainText(await formatInPage(page, cp.forecast_time))
  if (cp.weather) {
    await expect(popup).toContainText(`${cp.weather.wind_mph.toFixed(0)} mph`)
    await expect(popup).toContainText(`${cp.weather.rain_in_per_hr.toFixed(2)} in/hr`)
    await expect(popup).toContainText(`${cp.weather.snow_in_per_hr.toFixed(2)} in/hr`)
  }

  // Heatmap slider label vs requested departure
  const slider = page.getByRole('slider', { name: 'Forecast hours after departure' })
  await slider.fill('24')
  const moment = new Date(Date.parse(plan.inputs.departure_time) + 24 * 3_600_000).toISOString()
  await expect(page.getByRole('region', { name: 'Weather risk overlay' })).toContainText(await formatInPage(page, moment))

  if (process.env.E2E_SCREENSHOT_DIR) {
    await page.screenshot({ path: `${process.env.E2E_SCREENSHOT_DIR}/after-live-journey-1440.png` })
  }
  expect(problems).toEqual([])
})
