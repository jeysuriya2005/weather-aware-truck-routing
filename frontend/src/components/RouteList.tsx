import type { RouteOption, TripPlanResponse } from '../api/types'
import { formatDateTime } from '../lib/datetime'
import { formatAverageRisk } from '../lib/risk'
import { routeColor } from '../lib/routeColors'
import { formatDuration, formatMiles } from '../lib/units'
import { RiskBadge } from './RiskBadge'

interface Props {
  plan: TripPlanResponse
  selectedRouteId: string | null
  onSelect: (routeId: string) => void
}

function RouteRisk({ route }: { route: RouteOption }) {
  const summary = route.risk_summary
  if (!summary) {
    return <p className="route-card__risk-unknown">Weather risk unknown: forecast unavailable.</p>
  }
  const miles = summary.miles_by_level
  return (
    <>
      <div className="route-card__badges">
        <RiskBadge code={summary.max_risk} prefix="Worst:" />
        {summary.has_no_travel && <span className="tag tag--danger">Unsafe: No Travel</span>}
      </div>
      <dl className="route-card__stats route-card__stats--risk">
        <div>
          <dt>No Travel</dt>
          <dd>{formatMiles(miles.no_travel)}</dd>
        </div>
        <div>
          <dt>Severe</dt>
          <dd>{formatMiles(miles.severe)}</dd>
        </div>
        <div>
          <dt>High</dt>
          <dd>{formatMiles(miles.high)}</dd>
        </div>
        <div>
          <dt>Avg risk</dt>
          <dd>{formatAverageRisk(summary.average_risk)}</dd>
        </div>
        {summary.unknown_miles > 0 && (
          <div className="route-card__wide route-card__unknown">
            <dt>No forecast</dt>
            <dd>{formatMiles(summary.unknown_miles)} (unknown risk, not low)</dd>
          </div>
        )}
      </dl>
    </>
  )
}

export function RouteList({ plan, selectedRouteId, onSelect }: Props) {
  return (
    <section className="results" aria-label="Route options">
      <h2>
        {plan.route_count} route option{plan.route_count === 1 ? '' : 's'}
      </h2>

      {plan.notice && <p className="message message--info">{plan.notice}</p>}

      <ul className="route-list">
        {plan.routes.map((route) => {
          const selected = route.id === selectedRouteId
          return (
            <li key={route.id}>
              <button
                type="button"
                className={selected ? 'route-card is-selected' : 'route-card'}
                aria-pressed={selected}
                onClick={() => onSelect(route.id)}
              >
                <span className="route-card__title">
                  <span className="route-swatch" style={{ background: routeColor(route.index) }} aria-hidden />
                  {route.label}
                  {route.rank !== null && <span className="route-card__rank">#{route.rank}</span>}
                  {route.recommended && plan.recommendation.status === 'recommended' && (
                    <span className="tag tag--good">Recommended</span>
                  )}
                  {route.recommended && plan.recommendation.status === 'no_safe_route' && (
                    <span className="tag tag--danger">Least exposure</span>
                  )}
                </span>
                <dl className="route-card__stats">
                  <div>
                    <dt>Distance</dt>
                    <dd>{formatMiles(route.distance_miles)}</dd>
                  </div>
                  <div>
                    <dt>Drive time</dt>
                    <dd>{formatDuration(route.duration_seconds)}</dd>
                  </div>
                  <div className="route-card__wide">
                    <dt>ETA</dt>
                    <dd>{formatDateTime(route.arrival_time)}</dd>
                  </div>
                  {route.traffic_delay_seconds >= 60 && (
                    <div className="route-card__wide">
                      <dt>Traffic delay</dt>
                      <dd>{formatDuration(route.traffic_delay_seconds)} (included)</dd>
                    </div>
                  )}
                </dl>
                <RouteRisk route={route} />
              </button>
            </li>
          )
        })}
      </ul>

      {plan.weather_risk.status !== 'complete' && (
        <p className="message message--error" role="alert">
          {plan.weather_risk.message}
        </p>
      )}
    </section>
  )
}
