import type { Heatmap } from '../api/types'
import { formatDateTime } from '../lib/datetime'
import { frameCoverage } from '../lib/heatmap'
import { RiskLegend } from './RiskLegend'

interface Props {
  heatmap: Heatmap
  frame: number
  onFrameChange: (frame: number) => void
  visible: boolean
  onVisibleChange: (visible: boolean) => void
}

export function HeatmapControl({ heatmap, frame, onFrameChange, visible, onVisibleChange }: Props) {
  const maxFrame = heatmap.frame_offsets_hours.length - 1
  const offset = heatmap.frame_offsets_hours[frame] ?? frame
  const time = heatmap.frame_times[frame]
  const coverage = frameCoverage(heatmap, frame)

  return (
    <section className="map-overlay heatmap-control" aria-label="Weather risk overlay">
      <div className="heatmap-control__header">
        <label className="heatmap-control__toggle">
          <input type="checkbox" checked={visible} onChange={(event) => onVisibleChange(event.target.checked)} />
          Weather risk overlay
        </label>
        <span className="heatmap-control__time" aria-live="polite">
          Departure +{offset} h{time ? ` · ${formatDateTime(time)}` : ''}
        </span>
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
        aria-valuetext={`${offset} hours after departure`}
        disabled={!visible}
      />
      <div className="heatmap-control__scale" aria-hidden>
        <span>0 h</span>
        <span>24 h</span>
        <span>{maxFrame} h</span>
      </div>

      {heatmap.status === 'unavailable' ? (
        <p className="heatmap-control__note heatmap-control__note--warn">
          Forecast data is unavailable for the corridor. Grey means no data, not low risk.
        </p>
      ) : coverage < 1 ? (
        <p className="heatmap-control__note heatmap-control__note--warn">
          {Math.round((1 - coverage) * 100)}% of the corridor has no forecast for this hour (shown grey, not low risk).
        </p>
      ) : (
        <p className="heatmap-control__note">
          Conditions across the corridor at this hour, using your load weight. Checkpoint dots show each checkpoint's ETA forecast.
        </p>
      )}
      <RiskLegend />
    </section>
  )
}
