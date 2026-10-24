import type { RiskCode } from '../api/types'
import { riskColor, riskLabel, riskTint } from '../lib/risk'

export function RiskBadge({ code, prefix }: { code: RiskCode | null; prefix?: string }) {
  return (
    <span className={code ? 'risk-badge' : 'risk-badge risk-badge--unknown'} style={riskTint(code)}>
      <span className="risk-badge__dot" style={{ background: riskColor(code) }} aria-hidden />
      {prefix ? `${prefix} ` : ''}
      {riskLabel(code)}
    </span>
  )
}
