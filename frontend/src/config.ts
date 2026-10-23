// Public, non-secret runtime configuration. Never put API keys here:
// every VITE_* variable is embedded in the shipped JavaScript bundle.

export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? '/api'

// OpenFreeMap public vector style: no key, no registration.
// Attribution is added automatically by MapLibre from the style metadata.
export const MAP_STYLE_URL = 'https://tiles.openfreemap.org/styles/liberty'

// Initial view: contiguous United States.
export const INITIAL_VIEW = {
  center: [-98.5, 39.5] as [number, number],
  zoom: 3.6,
}
