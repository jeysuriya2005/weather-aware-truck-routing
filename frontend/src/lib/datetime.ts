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
