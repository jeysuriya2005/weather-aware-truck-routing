import { defineConfig } from '@playwright/test'

// Browser tests. Two projects:
//   mocked (default): every /api call is intercepted with deterministic fixtures
//                     (e2e/fixtures.ts) - repeatable, no backend or provider quota needed.
//   live:             real Django backend + TomTom + Open-Meteo through the Vite proxy
//                     (requires the backend on :8000 with TOMTOM_API_KEY; opt-in).
// Uses the locally installed Google Chrome (PW_CHANNEL to override), so no
// browser download is required. SwiftShader provides WebGL for MapLibre headlessly.
const PORT = Number(process.env.E2E_PORT ?? 5174)

export default defineConfig({
  testDir: './e2e',
  testMatch: /.*\.e2e\.ts/,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  // One worker by default: several headless Chromes rendering MapLibre with
  // software WebGL contend for CPU and make map-load waits flaky. E2E_WORKERS to override.
  workers: Number(process.env.E2E_WORKERS ?? 1),
  reporter: [['list']],
  use: {
    baseURL: `http://localhost:${PORT}`,
    channel: process.env.PW_CHANNEL ?? 'chrome',
    timezoneId: 'America/Denver',
    locale: 'en-US',
    launchOptions: { args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] },
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  webServer: {
    command: `npm run dev -- --port ${PORT} --strictPort`,
    url: `http://localhost:${PORT}`,
    reuseExistingServer: false,
    timeout: 60_000,
  },
  projects: [
    { name: 'mocked', testIgnore: /live\.e2e\.ts/ },
    { name: 'live', testMatch: /live\.e2e\.ts/, timeout: 180_000 },
  ],
})
