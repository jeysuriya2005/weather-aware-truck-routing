import { ApiError } from '../api/client'

export interface ErrorDescription {
  title: string
  details: string[]
}

// Request field names -> labels the driver sees in the form.
const FIELD_LABELS: Record<string, string> = {
  origin: 'Origin',
  destination: 'Destination',
  departure_time: 'Departure',
  load_weight_lb: 'Load weight',
  checkpoint_interval_miles: 'Weather checkpoints',
  q: 'Search',
  lat: 'latitude',
  lon: 'longitude',
}

const TITLES: Record<string, string> = {
  invalid_request: 'Please check the trip details',
  no_route_found: 'No drivable route found',
  provider_rejected_request: 'The routing service could not plan this trip',
  provider_not_configured: 'Routing is not configured on the server',
  provider_auth_failed: 'The routing service rejected the server credentials',
  provider_rate_limited: 'The routing service is busy',
  provider_timeout: 'The routing service timed out',
  provider_unavailable: 'The routing service is unavailable',
  provider_bad_response: 'The routing service returned an unexpected response',
  throttled: 'Too many requests',
  network_error: 'Cannot reach the server',
  internal_error: 'Unexpected server error',
}

/** Flattens DRF field errors, e.g. {origin: {lat: ["..."]}} -> ["Origin latitude: ..."]. */
export function flattenFieldErrors(fields: unknown, path: string[] = []): string[] {
  if (Array.isArray(fields)) {
    const label = path.map((part) => FIELD_LABELS[part] ?? part).join(' ')
    return fields.flatMap((item) =>
      typeof item === 'string' ? [label ? `${label}: ${item}` : item] : flattenFieldErrors(item, path),
    )
  }
  if (fields && typeof fields === 'object') {
    return Object.entries(fields).flatMap(([key, value]) =>
      flattenFieldErrors(value, key === 'non_field_errors' ? path : [...path, key]),
    )
  }
  return []
}

export function describeApiError(error: unknown): ErrorDescription {
  if (error instanceof ApiError) {
    const details = flattenFieldErrors(error.fields)
    return {
      title: TITLES[error.code] ?? 'Request failed',
      // Field reasons are more useful than the generic "Some fields are invalid."
      details: details.length ? details : [error.message],
    }
  }
  return { title: 'Something went wrong', details: ['Something went wrong while generating routes.'] }
}
