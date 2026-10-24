import type { Recommendation, RouteOption } from '../api/types'
import { formatDateTime } from '../lib/datetime'
import { HAZARD_LABELS, riskColor, riskLabel } from '../lib/risk'
import { formatDuration, formatMiles } from '../lib/units'
import { Icon, type IconName } from './Icon'

interface Props {
  recommendation: Recommendation
  routes: RouteOption[]
}

const TITLES: Record<Recommendation['status'], string> = {
  recommended: 'Recommended route',
  no_safe_route: 'No fully safe route',
  unavailable: 'No recommendation',
}

const ICONS: Record<Recommendation['status'], IconName> = {
  recommended: 'check',
  no_safe_route: 'alert',
  unavailable: 'info',
}

export function RecommendationPanel({ recommendation, routes }: Props) {
  const route = routes.find((r) => r.id === recommendation.route_id)
  const stretches = route?.hazard_stretches.slice(0, 3) ?? []

  return (
    <section className={`card recommendation recommendation--${recommendation.status}`} aria-label="Recommendation">
      <div className="recommendation__head">
        <span className="recommendation__icon">
          <Icon name={ICONS[recommendation.status]} size={20} />
        </span>
        <h2>
          {TITLES[recommendation.status]}
          {recommendation.status === 'recommended' && route ? `: ${route.label}` : ''}
          {recommendation.status === 'no_safe_route' && route ? ` (least exposure: ${route.label})` : ''}
        </h2>
      </div>

      {route && (
        <ul className="recommendation__facts" aria-label="Recommended route facts">
          <li>
            <Icon name="route" size={15} /> {formatMiles(route.distance_miles)}
          </li>
          <li>
            <Icon name="clock" size={15} /> {formatDuration(route.duration_seconds)}
          </li>
          <li>
            <Icon name="flag" size={15} /> {formatDateTime(route.arrival_time)}
          </li>
        </ul>
      )}

      <p className="recommendation__explanation">{recommendation.explanation}</p>

      {stretches.length > 0 && (
        <div className="recommendation__hazards">
          <h3>Significant hazards on {route?.label}</h3>
          <ul className="hazard-list">
            {stretches.map((s) => (
              <li key={`${s.first_index}-${s.level}`}>
                <span className="hazard-list__dot" style={{ background: riskColor(s.level) }} aria-hidden />
                <span>
                  <strong>{riskLabel(s.level)}</strong> {s.hazards.map((h) => HAZARD_LABELS[h].toLowerCase()).join(' + ')}, mi{' '}
                  {s.start_mile.toFixed(0)}–{s.end_mile.toFixed(0)} ({formatDateTime(s.first_eta)})
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {recommendation.status === 'recommended' && route && stretches.length === 0 && (
        <p className="recommendation__note">
          <Icon name="shield" size={15} /> No High, Severe or No Travel conditions forecast on this route.
        </p>
      )}

      {recommendation.warnings.map((warning) => (
        <p key={warning} className="notice notice--error notice--compact" role="alert">
          <Icon name="alert" />
          <span>{warning}</span>
        </p>
      ))}
    </section>
  )
}
