import type { DistributionSlice } from '../lib/insights'
import { formatShare } from '../lib/insights'
import { riskColor, riskLabel } from '../lib/risk'
import { formatMiles } from '../lib/units'

function sliceLabel(slice: DistributionSlice): string {
  return slice.code === 'unknown' ? 'No forecast' : riskLabel(slice.code)
}

/** Stacked bar of route miles per risk level; unknown miles are hatched grey, never green. */
export function RiskBar({ slices, showLegend = false }: { slices: DistributionSlice[]; showLegend?: boolean }) {
  const description = slices.map((s) => `${sliceLabel(s)} ${formatMiles(s.miles)} (${formatShare(s.share)})`).join(', ')
  return (
    <div className="risk-bar">
      <div className="risk-bar__track" role="img" aria-label={`Miles by risk level: ${description}`}>
        {slices.map((slice) => (
          <span
            key={slice.code}
            className={slice.code === 'unknown' ? 'risk-bar__slice risk-bar__slice--unknown' : 'risk-bar__slice'}
            style={{
              width: `${slice.share * 100}%`,
              background: slice.code === 'unknown' ? undefined : riskColor(slice.code),
            }}
            title={`${sliceLabel(slice)}: ${formatMiles(slice.miles)}`}
          />
        ))}
      </div>
      {showLegend && (
        <ul className="risk-bar__legend">
          {slices.map((slice) => (
            <li key={slice.code}>
              <span
                className={slice.code === 'unknown' ? 'risk-bar__key risk-bar__slice--unknown' : 'risk-bar__key'}
                style={{ background: slice.code === 'unknown' ? undefined : riskColor(slice.code) }}
                aria-hidden
              />
              {sliceLabel(slice)} <strong>{formatMiles(slice.miles)}</strong>
              <span className="risk-bar__share">{formatShare(slice.share)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
