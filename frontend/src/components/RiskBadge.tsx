import type { RiskCode } from '../api/types'
import { riskColor, riskLabel, riskTextColor } from '../lib/risk'

export function RiskBadge({ code, prefix }: { code: RiskCode | null; prefix?: string }) {
  return (
    <span
      className={code ? 'risk-badge' : 'risk-badge risk-badge--unknown'}
      style={{ background: riskColor(code), color: riskTextColor(code) }}
    >
      {prefix ? `${prefix} ` : ''}
      {riskLabel(code)}
    </span>
  )
}
