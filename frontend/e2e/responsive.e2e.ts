/**
 * Responsive layout checks at the assessment viewports (mocked data).
 * Set E2E_SCREENSHOT_DIR to save full-page screenshots for the QA report.
 */
import { expect, test } from '@playwright/test'
import { mockApi, planTrip, watchProblems } from './helpers.ts'

const VIEWPORTS = [
  [1920, 1080],
  [1440, 900],
  [1366, 768],
  [1024, 768],
  [768, 1024],
  [390, 844],
] as const

for (const [width, height] of VIEWPORTS) {
  test(`layout at ${width}x${height}`, async ({ page }) => {
    const problems = watchProblems(page)
    await page.setViewportSize({ width, height })
    await mockApi(page)
    await page.goto('/')
    await planTrip(page)
    await page.waitForTimeout(1500) // map fit + tiles

    const layout = await page.evaluate(() => {
      const doc = document.documentElement
      const rect = (selector: string) => document.querySelector(selector)?.getBoundingClientRect()
      const clipped = [...document.querySelectorAll('.route-card, .kpi, .card, .heatmap-control, .checkpoint-row')]
        .filter((el) => el.scrollWidth > el.clientWidth + 1).length
      return {
        overflow: doc.scrollWidth - doc.clientWidth,
        map: rect('.map'),
        header: rect('.app-header'),
        clipped,
      }
    })
    expect(layout.overflow, 'horizontal page overflow').toBeLessThanOrEqual(0)
    expect(layout.clipped, 'elements with clipped content').toBe(0)
    expect(layout.map!.width).toBeGreaterThanOrEqual(width < 900 ? width - 40 : 500)
    expect(layout.map!.height).toBeGreaterThanOrEqual(300)

    for (const name of ['Recommendation', 'Route options', 'Weather risk overlay']) {
      const region = page.getByRole('region', { name })
      await region.scrollIntoViewIfNeeded()
      await expect(region).toBeVisible()
    }
    await expect(page.getByRole('slider', { name: 'Forecast hours after departure' })).toBeVisible()

    if (process.env.E2E_SCREENSHOT_DIR) {
      await page.evaluate(() => window.scrollTo(0, 0))
      // "fixture-" prefix: these show deterministic TEST data, not live forecasts.
      await page.screenshot({ path: `${process.env.E2E_SCREENSHOT_DIR}/fixture-results-${width}x${height}.png`, fullPage: width < 900 })
    }
    expect(problems).toEqual([])
  })
}
