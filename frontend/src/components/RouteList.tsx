import type { RouteOption, TripPlanResponse } from '../api/types'
import { formatDateTime } from '../lib/datetime'
import { formatShare, routeInsights } from '../lib/insights'
import { formatAverageRisk } from '../lib/risk'
import { routeColor } from '../lib/routeColors'
import { formatDuration, formatMiles } from '../lib/units'
import { Icon } from './Icon'
import { RiskBadge } from './RiskBadge'
import { RiskBar } from './RiskBar'

interface Props {
  plan: TripPlanResponse
  selectedRouteId: string | null
  onSelect: (routeId: string) => void
}

function RouteRisk({ route }: { route: RouteOption }) {
  const summary = route.risk_summary
  if (!summary) {
    return (
      <p className="route-card__risk-unknown">
        <Icon name="info" size={15} /> Weather risk unknown: forecast unavailable.
      </p>
    )
  }
  const insights = routeInsights(route)
  const coverage = insights.checkpointsTotal ? insights.checkpointsWithForecast / insights.checkpointsTotal : 0
  return (
    <>
      <div className="route-card__badges">
        <RiskBadge code={summary.max_risk} prefix="Worst:" />
        {summary.has_no_travel && (
          <span className="tag tag--danger">
            No Travel {formatMiles(summary.miles_by_level.no_travel)}
          </span>
        )}
      </div>
      <dl className="metric-grid">
        <div>
          <dt>Avg risk</dt>
          <dd>{formatAverageRisk(summary.average_risk)}</dd>
        </div>
        <div>
          <dt>High</dt>
          <dd>{formatMiles(summary.miles_by_level.high)}</dd>
        </div>
        <div>
          <dt>Severe+</dt>
          <dd>{formatMiles(summary.severe_or_worse_miles)}</dd>
        </div>
        <div>
          <dt>Coverage</dt>
          <dd title={`${insights.checkpointsWithForecast} of ${insights.checkpointsTotal} checkpoints have a forecast`}>
            {formatShare(coverage)}
          </dd>
        </div>
      </dl>
      <RiskBar slices={insights.distribution} />
      {summary.unknown_miles > 0 && (
        <p className="route-card__unknown">
          No forecast: {formatMiles(summary.unknown_miles)} (unknown risk, not low)
        </p>
      )}
    </>
  )
}

function StatusTag({ route, plan }: { route: RouteOption; plan: TripPlanResponse }) {
  if (route.recommended && plan.recommendation.status === 'recommended') {
    return <span className="tag tag--good">Recommended</span>
  }
  if (route.recommended && plan.recommendation.status === 'no_safe_route') {
    return <span className="tag tag--danger">Least exposure</span>
  }
  if (route.risk_summary?.has_no_travel) return <span className="tag tag--danger">Unsafe: No Travel</span>
  return null
}

export function RouteList({ plan, selectedRouteId, onSelect }: Props) {
  return (
    <section className="results" aria-label="Route options">
      <div className="section-heading">
        <h2>Route comparison</h2>
        <span className="section-heading__meta">
          {plan.route_count} route option{plan.route_count === 1 ? '' : 's'}
        </span>
      </div>

      {plan.notice && (
        <p className="notice notice--info notice--compact">
          <Icon name="info" />
          <span>{plan.notice}</span>
        </p>
      )}
      {(plan.weather_risk.forecast_grid_degrees ?? 0.05) > 0.05 && (
        <p className="notice notice--info notice--compact">
          <Icon name="info" />
          <span>
            Long trip: checkpoints are still every {plan.inputs.checkpoint_interval_miles} mi, but forecasts are read from a{' '}
            {plan.weather_risk.forecast_grid_degrees}° grid (about {Math.round(plan.weather_risk.forecast_grid_degrees! * 111)} km)
            to stay within the weather provider's request limits.
          </span>
        </p>
      )}

      <ul className="route-list">
        {plan.routes.map((route) => {
          const selected = route.id === selectedRouteId
          const classes = ['route-card', selected && 'is-selected', route.recommended && 'is-recommended']
          return (
            <li key={route.id}>
              <button
                type="button"
                className={classes.filter(Boolean).join(' ')}
                aria-pressed={selected}
                onClick={() => onSelect(route.id)}
              >
                <span className="route-card__title">
                  <span className="route-swatch" style={{ background: routeColor(route.index) }} aria-hidden />
                  <span className="route-card__name">{route.label}</span>
                  {route.rank !== null && <span className="route-card__rank">#{route.rank}</span>}
                  <StatusTag route={route} plan={plan} />
                </span>
                <dl className="route-card__trip">
                  <div>
                    <dt>
                      <Icon name="route" size={14} /> Distance
                    </dt>
                    <dd>{formatMiles(route.distance_miles)}</dd>
                  </div>
                  <div>
                    <dt>
                      <Icon name="clock" size={14} /> Drive time
                    </dt>
                    <dd>{formatDuration(route.duration_seconds)}</dd>
                  </div>
                  <div className="route-card__eta">
                    <dt>
                      <Icon name="flag" size={14} /> ETA
                    </dt>
                    <dd>{formatDateTime(route.arrival_time)}</dd>
                  </div>
                </dl>
                {route.traffic_delay_seconds >= 60 && (
                  <p className="route-card__traffic">Includes {formatDuration(route.traffic_delay_seconds)} traffic delay</p>
                )}
                <RouteRisk route={route} />
              </button>
            </li>
          )
        })}
      </ul>

      {plan.weather_risk.status !== 'complete' && (
        <p className="notice notice--error notice--compact" role="alert">
          {plan.weather_risk.message}
        </p>
      )}
    </section>
  )
}
