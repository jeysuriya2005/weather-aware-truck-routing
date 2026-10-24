// <input type="datetime-local"> works in the browser's local time without an
// offset; the API requires an explicit offset, so convert at the boundary.

const pad = (value: number) => String(value).padStart(2, '0')

/** Date -> "YYYY-MM-DDTHH:mm" in local time, for datetime-local inputs. */
export function toLocalInputValue(date: Date): string {
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  )
}

/** "YYYY-MM-DDTHH:mm" (local) -> ISO 8601 in UTC, or null if invalid. */
export function localInputToIso(value: string): string | null {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) return null
  const date = new Date(value) // date-time strings without offset are parsed as local time
  return Number.isNaN(date.getTime()) ? null : date.toISOString()
}

/** Next quarter hour from now: a sensible default departure. */
export function defaultDeparture(now: Date = new Date()): Date {
  const date = new Date(now)
  date.setSeconds(0, 0)
  date.setMinutes(Math.ceil((date.getMinutes() + 1) / 15) * 15)
  return date
}

// Mirrors backend/trips/serializers.py: 15 min in the past to 13 days ahead.
export const DEPARTURE_PAST_TOLERANCE_MS = 15 * 60_000
export const DEPARTURE_MAX_AHEAD_MS = 13 * 24 * 3_600_000

/** Allowed departure range as datetime-local strings (min rounded up to the minute). */
export function departureBounds(now: Date = new Date()): { min: string; max: string } {
  const min = new Date(now.getTime() - DEPARTURE_PAST_TOLERANCE_MS + 60_000)
  const max = new Date(now.getTime() + DEPARTURE_MAX_AHEAD_MS)
  return { min: toLocalInputValue(min), max: toLocalInputValue(max) }
}

/** Client-side check before the request; the server re-validates. */
export function departureProblem(iso: string, now: Date = new Date()): string | null {
  const t = new Date(iso).getTime()
  if (t < now.getTime() - DEPARTURE_PAST_TOLERANCE_MS) return 'Departure cannot be in the past.'
  if (t > now.getTime() + DEPARTURE_MAX_AHEAD_MS) {
    return 'Departure must be within 13 days so forecasts cover the trip and the 48-hour outlook.'
  }
  return null
}

/** Short local time, e.g. "Sat 4:00 PM". */
export function formatShortTime(iso: string): string {
  return new Date(iso).toLocaleString('en-US', { weekday: 'short', hour: 'numeric', minute: '2-digit' })
}

/** Formats an API timestamp in the viewer's local time with a zone name. */
export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZoneName: 'short',
  })
}
