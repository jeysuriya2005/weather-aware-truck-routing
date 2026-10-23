import { RISK_LEVELS, UNKNOWN_COLOR, UNKNOWN_LABEL } from '../lib/risk'

export function RiskLegend() {
  return (
    <ul className="risk-legend" aria-label="Risk level legend">
      {RISK_LEVELS.map((level) => (
        <li key={level.code}>
          <span className="risk-legend__swatch" style={{ background: level.color }} aria-hidden />
          {level.label}
        </li>
      ))}
      <li>
        <span className="risk-legend__swatch risk-legend__swatch--unknown" style={{ background: UNKNOWN_COLOR }} aria-hidden />
        {UNKNOWN_LABEL}
      </li>
    </ul>
  )
}
