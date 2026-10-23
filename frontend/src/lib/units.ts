// The UI works in miles, mph and pounds, matching the assessment.

export const METERS_PER_MILE = 1609.344

export function metersToMiles(meters: number): number {
  return meters / METERS_PER_MILE
}

export function formatMiles(miles: number): string {
  const digits = miles < 100 ? 1 : 0
  return `${miles.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })} mi`
}

/** 51,060 s -> "14 h 11 min"; rounds to the nearest minute. */
export function formatDuration(totalSeconds: number): string {
  const totalMinutes = Math.round(totalSeconds / 60)
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  if (hours === 0) return `${minutes} min`
  return minutes === 0 ? `${hours} h` : `${hours} h ${minutes} min`
}

export function formatPounds(pounds: number): string {
  return `${pounds.toLocaleString('en-US')} lb`
}
