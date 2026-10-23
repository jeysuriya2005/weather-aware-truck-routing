import type { Recommendation, RouteOption } from '../api/types'
import { formatDateTime } from '../lib/datetime'
import { HAZARD_LABELS, riskLabel } from '../lib/risk'

interface Props {
  recommendation: Recommendation
  routes: RouteOption[]
}

const TITLES: Record<Recommendation['status'], string> = {
  recommended: 'Recommended route',
  no_safe_route: 'No fully safe route',
  unavailable: 'No recommendation',
}

export function RecommendationPanel({ recommendation, routes }: Props) {
  const route = routes.find((r) => r.id === recommendation.route_id)
  const stretches = route?.hazard_stretches.slice(0, 3) ?? []

  return (
    <section className={`recommendation recommendation--${recommendation.status}`} aria-label="Recommendation">
      <h2>
        {TITLES[recommendation.status]}
        {recommendation.status === 'recommended' && route ? `: ${route.label}` : ''}
        {recommendation.status === 'no_safe_route' && route ? ` (least exposure: ${route.label})` : ''}
      </h2>
      <p>{recommendation.explanation}</p>

      {stretches.length > 0 && (
        <div>
          <h3>Significant hazards on {route?.label}</h3>
          <ul className="hazard-list">
            {stretches.map((s) => (
              <li key={`${s.first_index}-${s.level}`}>
                <strong>{riskLabel(s.level)}</strong> {s.hazards.map((h) => HAZARD_LABELS[h].toLowerCase()).join(' + ')}, mi{' '}
                {s.start_mile.toFixed(0)}–{s.end_mile.toFixed(0)} ({formatDateTime(s.first_eta)})
              </li>
            ))}
          </ul>
        </div>
      )}
      {recommendation.status === 'recommended' && route && stretches.length === 0 && (
        <p className="recommendation__note">No High, Severe or No Travel conditions forecast on this route.</p>
      )}

      {recommendation.warnings.map((warning) => (
        <p key={warning} className="message message--error" role="alert">
          {warning}
        </p>
      ))}
    </section>
  )
}
