import { API_BASE_URL } from '../config'
import type { ApiErrorBody, Place, TripPlanRequest, TripPlanResponse } from './types'

export interface HealthResponse {
  status: 'ok'
  service: string
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly fields?: Record<string, unknown>

  constructor(status: number, code: string, message: string, fields?: Record<string, unknown>) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.fields = fields
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, init)
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError(0, 'network_error', 'Could not reach the server. Check that the API is running.')
  }

  if (response.ok) return (await response.json()) as T

  let body: Partial<ApiErrorBody> = {}
  try {
    body = (await response.json()) as ApiErrorBody
  } catch {
    // Non-JSON error page (e.g. a proxy); fall through to a generic message.
  }
  throw new ApiError(
    response.status,
    body.error?.code ?? 'http_error',
    body.error?.message ?? `Request failed (HTTP ${response.status}).`,
    body.error?.fields,
  )
}

export function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return request<HealthResponse>('/health/', { signal })
}

export async function geocode(query: string, signal?: AbortSignal): Promise<Place[]> {
  const params = new URLSearchParams({ q: query })
  const data = await request<{ results: Place[] }>(`/geocode/?${params}`, { signal })
  return data.results
}

export function planTrip(body: TripPlanRequest, signal?: AbortSignal): Promise<TripPlanResponse> {
  return request<TripPlanResponse>('/trips/plan/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })
}
