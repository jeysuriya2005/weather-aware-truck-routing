import type { CSSProperties } from 'react'
import type { Heatmap } from '../api/types'
import { formatDateTime, formatShortTime } from '../lib/datetime'
import { frameCoverage, frameLabel } from '../lib/heatmap'
import { formatShare } from '../lib/insights'
import { Icon } from './Icon'
import { RiskLegend } from './RiskLegend'

interface Props {
  heatmap: Heatmap
  /** Requested departure (ISO); frame N refers to departure + N hours. */
  departureTime: string
  frame: number
  onFrameChange: (frame: number) => void
  visible: boolean
  onVisibleChange: (visible: boolean) => void
}

export function HeatmapControl({ heatmap, departureTime, frame, onFrameChange, visible, onVisibleChange }: Props) {
  const maxFrame = heatmap.frame_offsets_hours.length - 1
  const label = frameLabel(heatmap, departureTime, frame)
  const coverage = frameCoverage(heatmap, frame)

  return (
    <section className="map-overlay heatmap-control" aria-label="Weather risk overlay">
      <div className="heatmap-control__header">
        <label className="switch">
          <input type="checkbox" checked={visible} onChange={(event) => onVisibleChange(event.target.checked)} />
          <span className="switch__track" aria-hidden />
          <span className="switch__label">
            <Icon name="layers" size={15} /> Weather risk overlay
          </span>
        </label>
        <div className="heatmap-control__time" aria-live="polite">
          <strong>Shading at departure +{label.offsetHours} h</strong>
          <span> · {formatDateTime(label.moment)}</span>
        </div>
      </div>

      <input
        type="range"
        className="heatmap-control__slider"
        min={0}
        max={maxFrame}
        step={1}
        value={frame}
        onChange={(event) => onFrameChange(Number(event.target.value))}
        aria-label="Forecast hours after departure"
        aria-valuetext={`${label.offsetHours} hours after departure`}
        disabled={!visible}
        style={{ '--fill': `${(frame / Math.max(maxFrame, 1)) * 100}%` } as CSSProperties}
      />
      <div className="heatmap-control__scale" aria-hidden>
        <span>0 h</span>
        <span>12 h</span>
        <span>24 h</span>
        <span>36 h</span>
        <span>{maxFrame} h</span>
      </div>

      <div className="heatmap-control__footer">
        {heatmap.status === 'unavailable' ? (
          <p className="heatmap-control__note heatmap-control__note--warn">
            <Icon name="alert" size={14} /> Forecast data is unavailable for the corridor. Grey means no data, not low risk.
          </p>
        ) : coverage < 1 ? (
          <p className="heatmap-control__note heatmap-control__note--warn">
            <Icon name="alert" size={14} /> {formatShare(1 - coverage)} of the corridor has no forecast for this hour (shown grey,
            not low risk).
          </p>
        ) : (
          <p className="heatmap-control__note">
            {label.forecastHour ? `Forecast hour ending ${formatShortTime(label.forecastHour)}. ` : ''}Shading = area risk at
            this hour (click it for details). Dots = risk when the truck reaches each checkpoint, so they can differ.
          </p>
        )}
        <RiskLegend />
      </div>
    </section>
  )
}
