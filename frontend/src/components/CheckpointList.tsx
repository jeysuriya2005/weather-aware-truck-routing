import type { RouteOption } from '../api/types'
import { checkpointRows } from '../lib/checkpoints'
import { formatDateTime } from '../lib/datetime'
import { RiskBadge } from './RiskBadge'

interface Props {
  route: RouteOption
  selectedIndex: number | null
  onSelect: (index: number) => void
}

export function CheckpointList({ route, selectedIndex, onSelect }: Props) {
  const selected = route.checkpoints.find((cp) => cp.index === selectedIndex) ?? null

  return (
    <section className="checkpoints" aria-label={`${route.label} checkpoints`}>
      <h2>
        {route.label} checkpoints ({route.checkpoints.length})
      </h2>
      {route.eta_source === 'proportional_estimate' && (
        <p className="message message--info">
          ETAs are estimated in proportion to distance: the routing provider gave no timing detail.
        </p>
      )}

      {selected && (
        <div className="checkpoint-detail" aria-live="polite">
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
              {warning}
            </p>
          ))}
        </div>
      )}

      <ol className="checkpoint-list">
        {route.checkpoints.map((cp) => (
          <li key={cp.index}>
            <button
              type="button"
              className={cp.index === selectedIndex ? 'checkpoint-row is-selected' : 'checkpoint-row'}
              onClick={() => onSelect(cp.index)}
            >
              <span className="checkpoint-row__mile">mi {cp.mile.toFixed(0)}</span>
              <span className="checkpoint-row__eta">{formatDateTime(cp.eta)}</span>
              <RiskBadge code={cp.risk?.overall ?? null} />
            </button>
          </li>
        ))}
      </ol>
    </section>
  )
}
