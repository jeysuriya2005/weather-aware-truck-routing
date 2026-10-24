import { expect, type Page } from '@playwright/test'
import type { TripPlanResponse } from '../src/api/types.ts'
import { geocodeResults, planFixture } from './fixtures.ts'

/** Collects page errors, console errors and failed /api requests (excluding deliberate aborts). */
export function watchProblems(page: Page): string[] {
  const problems: string[] = []
  page.on('pageerror', (error) => problems.push(`pageerror: ${error.message}`))
  page.on('console', (message) => {
    if (message.type() !== 'error') return
    const text = message.text()
    // Deliberate HTTP error fixtures surface as "Failed to load resource" in Chrome.
    if (text.startsWith('Failed to load resource')) return
    problems.push(`console: ${text}`)
  })
  return problems
}

export interface MockOptions {
  plan?: TripPlanResponse | (() => TripPlanResponse)
  planStatus?: number
  planBody?: unknown
  planDelayMs?: number
  abortPlan?: boolean
}

/** Intercepts every /api call with fixtures; returns the list of plan request bodies. */
export async function mockApi(page: Page, options: MockOptions = {}): Promise<unknown[]> {
  const planRequests: unknown[] = []
  await page.route('**/api/health/', (route) =>
    route.fulfill({ json: { status: 'ok', service: 'weather-aware-truck-routing' } }))
  await page.route('**/api/geocode/**', (route) => {
    const q = new URL(route.request().url()).searchParams.get('q') ?? ''
    return route.fulfill({ json: { results: geocodeResults(q) } })
  })
  await page.route('**/api/trips/plan/', async (route) => {
    planRequests.push(route.request().postDataJSON())
    if (options.planDelayMs) await new Promise((resolve) => setTimeout(resolve, options.planDelayMs))
    if (options.abortPlan) return route.abort('connectionrefused')
    if (options.planStatus && options.planStatus !== 200) {
      return route.fulfill({ status: options.planStatus, json: options.planBody })
    }
    const plan = typeof options.plan === 'function' ? options.plan() : (options.plan ?? planFixture())
    return route.fulfill({ json: plan })
  })
  return planRequests
}

/** Suggestion options only; a bare getByRole('option') also matches the <select>'s options. */
export function suggestions(page: Page) {
  return page.getByRole('listbox').getByRole('option')
}

export async function pickPlace(page: Page, label: 'Origin' | 'Destination', text: string) {
  await page.getByLabel(label, { exact: true }).fill(text)
  await suggestions(page).first().click()
}

export async function fillTrip(page: Page, load = '38000') {
  await pickPlace(page, 'Origin', 'Dallas')
  await pickPlace(page, 'Destination', 'Denver')
  await page.getByLabel('Load weight (lb)').fill(load)
}

export async function planTrip(page: Page) {
  await fillTrip(page)
  await page.getByRole('button', { name: 'Generate Routes' }).click()
  await expect(page.getByRole('region', { name: 'Recommendation' })).toBeVisible()
  await waitForMap(page)
}

/** MapLibre loads its style from OpenFreeMap; wait until sources/layers exist. */
export async function waitForMap(page: Page) {
  await expect(page.locator('.map')).toHaveAttribute('data-map-ready', 'true', { timeout: 30_000 })
}

/** Formats in the page (same timezone/locale as the app), mirroring src/lib/datetime.ts. */
export function formatInPage(page: Page, iso: string, short = false): Promise<string> {
  return page.evaluate(
    ([value, isShort]) =>
      new Date(value).toLocaleString(
        'en-US',
        isShort
          ? { weekday: 'short', hour: 'numeric', minute: '2-digit' }
          : { weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZoneName: 'short' },
      ),
    [iso, short] as const,
  )
}
