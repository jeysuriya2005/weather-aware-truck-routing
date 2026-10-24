import { Icon } from './Icon'

/** Shown on the map before any trip is planned. */
export function MapEmptyState() {
  return (
    <div className="map-overlay map-empty" role="note">
      <span className="map-empty__icon">
        <Icon name="route" size={26} />
      </span>
      <h2>Plan a trip to compare routes</h2>
      <ol>
        <li>Choose an origin and destination</li>
        <li>Set departure time and load weight</li>
        <li>Generate routes to see weather risk along each one</li>
      </ol>
    </div>
  )
}

/** Real elapsed time while the plan request runs; no simulated progress. */
export function MapLoading({ seconds }: { seconds: number }) {
  return (
    <div className="map-overlay map-loading" role="status" aria-live="polite">
      <span className="spinner spinner--dark" aria-hidden />
      <div>
        <strong>Calculating truck routes and checkpoint forecasts…</strong>
        <span>
          {seconds} s elapsed · regional trips usually 5–15 s, coast-to-coast up to about a minute
        </span>
      </div>
    </div>
  )
}
