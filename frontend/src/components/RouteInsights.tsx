import type { ReactNode } from 'react'
import type { Heatmap, RouteOption } from '../api/types'
import { formatShortTime } from '../lib/datetime'
import { formatShare, routeInsights, type Peak } from '../lib/insights'
import { HAZARD_LABELS, riskColor, riskLabel } from '../lib/risk'
import { routeColor } from '../lib/routeColors'
import { formatMiles } from '../lib/units'
import { CheckpointList } from './CheckpointList'
import { Icon, type IconName } from './Icon'
import { RiskBadge } from './RiskBadge'
import { RiskBar } from './RiskBar'

interface Props {
  route: RouteOption
  selectedCheckpoint: number | null
  onSelectCheckpoint: (index: number) => void
  overlayFrame?: number
  heatmap?: Heatmap | null
  onShowFrame?: (frame: number) => void
}

function Tile({ icon, label, children, footnote }: { icon: IconName; label: string; children: ReactNode; footnote?: string }) {
  return (
    <div className="kpi">
      <span className="kpi__label">
        <Icon name={icon} size={15} /> {label}
      </span>
      <span className="kpi__value">{children}</span>
      {footnote && <span className="kpi__foot">{footnote}</span>}
    </div>
  )
}

function where(peak: Peak): string {
  return `mi ${peak.checkpoint.mile.toFixed(0)} · ${formatShortTime(peak.checkpoint.eta)}`
}

function PeakValue({ peak, unit, digits }: { peak: Peak | null; unit: string; digits: number }) {
  if (!peak) return <span className="kpi__none">No forecast</span>
  return (
    <>
      {peak.value.toFixed(digits)}
      <small> {unit}</small>
    </>
  )
}

export function RouteInsights({ route, selectedCheckpoint, onSelectCheckpoint, overlayFrame, heatmap, onShowFrame }: Props) {
  const insights = routeInsights(route)
  const { peakWind, peakGust, peakRain, peakSnow } = insights
  const coverage = insights.checkpointsTotal ? insights.checkpointsWithForecast / insights.checkpointsTotal : 0

  return (
    <section className="insights-panel" aria-label={`${route.label} weather`}>
      <div className="section-heading">
        <h2>
          <span className="route-swatch" style={{ background: routeColor(route.index) }} aria-hidden />
          {route.label} weather
        </h2>
        <span className="section-heading__meta">at each checkpoint's ETA</span>
      </div>

      <div className="kpi-grid">
        <Tile
          icon="wind"
          label="Peak wind"
          footnote={peakWind ? `${where(peakWind)}${peakGust ? ` · gusts to ${peakGust.value.toFixed(0)} mph` : ''}` : undefined}
        >
          <PeakValue peak={peakWind} unit="mph" digits={0} />
        </Tile>
        <Tile icon="rain" label="Peak rain" footnote={peakRain && peakRain.value > 0 ? where(peakRain) : undefined}>
          <PeakValue peak={peakRain} unit="in/hr" digits={2} />
        </Tile>
        <Tile icon="snow" label="Peak snow" footnote={peakSnow && peakSnow.value > 0 ? where(peakSnow) : undefined}>
          <PeakValue peak={peakSnow} unit="in/hr" digits={2} />
        </Tile>
        <Tile icon="gauge" label="Worst risk">
          <RiskBadge code={insights.worst} />
        </Tile>
        <Tile
          icon="alert"
          label="High or worse"
          footnote={insights.highOrWorseMiles === null ? undefined : `of ${formatMiles(route.distance_miles)}`}
        >
          {insights.highOrWorseMiles === null ? <span className="kpi__none">Unknown</span> : formatMiles(insights.highOrWorseMiles)}
        </Tile>
        <Tile
          icon="signal"
          label="Forecast coverage"
          footnote={`${insights.checkpointsWithForecast} of ${insights.checkpointsTotal} checkpoints`}
        >
          {formatShare(coverage)}
        </Tile>
      </div>

      <div className="insights-panel__block">
        <h3>Miles by risk level</h3>
        <RiskBar slices={insights.distribution} showLegend />
      </div>

      {route.hazard_stretches.length > 0 && (
        <div className="insights-panel__block">
          <h3>Hazard stretches</h3>
          <ul className="hazard-list">
            {route.hazard_stretches.map((s) => (
              <li key={`${s.first_index}-${s.level}`}>
                <span className="hazard-list__dot" style={{ background: riskColor(s.level) }} aria-hidden />
                <span>
                  <strong>{riskLabel(s.level)}</strong> {s.hazards.map((h) => HAZARD_LABELS[h].toLowerCase()).join(' + ')} · mi{' '}
                  {s.start_mile.toFixed(0)}–{s.end_mile.toFixed(0)} · {formatShortTime(s.first_eta)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <CheckpointList
        route={route}
        selectedIndex={selectedCheckpoint}
        onSelect={onSelectCheckpoint}
        overlayFrame={overlayFrame}
        heatmap={heatmap}
        onShowFrame={onShowFrame}
      />
    </section>
  )
}
