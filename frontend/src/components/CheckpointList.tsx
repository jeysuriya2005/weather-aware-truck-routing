import type { CSSProperties } from 'react'
import type { Checkpoint, Heatmap, RouteOption } from '../api/types'
import { checkpointRows } from '../lib/checkpoints'
import { formatShortTime } from '../lib/datetime'
import { frameForForecastHour } from '../lib/heatmap'
import { riskColor } from '../lib/risk'
import { Icon } from './Icon'
import { RiskBadge } from './RiskBadge'

interface Props {
  route: RouteOption
  selectedIndex: number | null
  onSelect: (index: number) => void
  /** Overlay frame currently shown (hours after departure) and the plan's heatmap. */
  overlayFrame?: number
  heatmap?: Heatmap | null
  onShowFrame?: (frame: number) => void
}

/** Explains whether the map shading shows the same hour as this checkpoint's forecast. */
function OverlayRelation({ cp, overlayFrame, heatmap, onShowFrame }: {
  cp: Checkpoint
  overlayFrame: number
  heatmap: Heatmap
  onShowFrame?: (frame: number) => void
}) {
  const etaFrame = frameForForecastHour(heatmap, cp.forecast_time)
  if (etaFrame === null) {
    return (
      <p className="overlay-relation">
        <Icon name="info" size={14} /> This checkpoint is reached after the 48-hour shading window.
      </p>
    )
  }
  if (etaFrame === overlayFrame) {
    return (
      <p className="overlay-relation overlay-relation--match">
        <Icon name="check" size={14} /> Map shading shows this checkpoint's forecast hour (departure +{etaFrame} h).
      </p>
    )
  }
  return (
    <div className="overlay-relation">
      <span>
        <Icon name="info" size={14} /> Map shading shows departure +{overlayFrame} h; the truck reaches this checkpoint at
        +{etaFrame} h, so colours can differ.
      </span>
      {onShowFrame && (
        <button type="button" className="popup-action" onClick={() => onShowFrame(etaFrame)}>
          Show shading at this ETA (+{etaFrame} h)
        </button>
      )}
    </div>
  )
}

export function CheckpointList({ route, selectedIndex, onSelect, overlayFrame, heatmap, onShowFrame }: Props) {
  const selected = route.checkpoints.find((cp) => cp.index === selectedIndex) ?? null

  return (
    <section className="checkpoints" aria-label={`${route.label} checkpoints`}>
      <div className="section-heading">
        <h3>
          {route.label} checkpoints ({route.checkpoints.length})
        </h3>
      </div>
      {route.eta_source === 'proportional_estimate' && (
        <p className="notice notice--info notice--compact">
          <Icon name="info" />
          <span>ETAs are estimated in proportion to distance: the routing provider gave no timing detail.</span>
        </p>
      )}

      {selected && (
        <div className="checkpoint-detail" aria-live="polite">
          <div className="checkpoint-detail__head">
            <strong>Checkpoint {selected.index + 1}</strong>
            <RiskBadge code={selected.risk?.overall ?? null} />
          </div>
          <dl>
            {checkpointRows(selected).map((row) => (
              <div key={row.label}>
                <dt>{row.label}</dt>
                <dd>{row.value}</dd>
              </div>
            ))}
          </dl>
          {selected.warnings.map((warning) => (
            <p key={warning} className="checkpoint-detail__warning">
              <Icon name="alert" size={14} /> {warning}
            </p>
          ))}
          {heatmap && overlayFrame !== undefined && (
            <OverlayRelation cp={selected} overlayFrame={overlayFrame} heatmap={heatmap} onShowFrame={onShowFrame} />
          )}
        </div>
      )}

      <div className="checkpoint-table">
        <div className="checkpoint-table__head" aria-hidden>
          <span>Mile</span>
          <span>ETA</span>
          <span>Wind</span>
          <span>Risk</span>
        </div>
        <ol className="checkpoint-list">
          {route.checkpoints.map((cp) => (
            <li key={cp.index}>
              <button
                type="button"
                className={cp.index === selectedIndex ? 'checkpoint-row is-selected' : 'checkpoint-row'}
                onClick={() => onSelect(cp.index)}
                style={{ '--row-accent': riskColor(cp.risk?.overall ?? null) } as CSSProperties}
              >
                <span className="checkpoint-row__mile">mi {cp.mile.toFixed(0)}</span>
                <span className="checkpoint-row__eta">{formatShortTime(cp.eta)}</span>
                <span className="checkpoint-row__wind">{cp.weather ? `${cp.weather.wind_mph.toFixed(0)} mph` : '—'}</span>
                <RiskBadge code={cp.risk?.overall ?? null} />
              </button>
            </li>
          ))}
        </ol>
      </div>
    </section>
  )
}
