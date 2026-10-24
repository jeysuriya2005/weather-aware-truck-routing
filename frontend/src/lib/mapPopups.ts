// DOM builders for map popups (text nodes only: no HTML injection).
import type { Checkpoint, Heatmap } from '../api/types'
import { checkpointRows } from './checkpoints'
import { formatDateTime } from './datetime'
import { cellForecast, frameLabel } from './heatmap'
import { riskCodeFromScore, riskColor, riskLabel } from './risk'

function detailList(rows: { label: string; value: string }[]): HTMLElement {
  const list = document.createElement('dl')
  for (const row of rows) {
    const item = document.createElement('div')
    const dt = document.createElement('dt')
    dt.textContent = row.label
    const dd = document.createElement('dd')
    dd.textContent = row.value
    item.append(dt, dd)
    list.append(item)
  }
  return list
}

/** Popup for a shaded corridor cell: the AREA forecast at the slider hour (text nodes only). */
export function cellPopupContent(heatmap: Heatmap, departureIso: string, frame: number, index: number): HTMLElement {
  const cell = cellForecast(heatmap, index, frame)
  const label = frameLabel(heatmap, departureIso, frame)
  const code = riskCodeFromScore(cell.risk)
  const root = document.createElement('div')
  root.className = 'checkpoint-popup cell-popup'
  root.style.setProperty('--popup-accent', riskColor(code))
  const title = document.createElement('strong')
  title.className = 'checkpoint-popup__title'
  title.textContent = `Shading at departure +${label.offsetHours} h: ${riskLabel(code)}`
  root.append(title)
  const rows = [
    { label: 'Time', value: formatDateTime(label.moment) },
    { label: 'Forecast hour', value: label.forecastHour ? formatDateTime(label.forecastHour) : '—' },
  ]
  if (cell.risk === null) {
    rows.push({ label: 'Risk', value: 'Unknown: no forecast for this hour' })
  } else {
    rows.push(
      { label: 'Wind', value: `${cell.windMph?.toFixed(0)} mph` },
      { label: 'Rain', value: `${cell.rainInPerHr?.toFixed(2)} in/hr` },
      { label: 'Snow', value: `${cell.snowInPerHr?.toFixed(2)} in/hr` },
    )
  }
  rows.push({ label: 'Area', value: `${heatmap.spacing_degrees}° cell at ${cell.lat.toFixed(2)}, ${cell.lon.toFixed(2)}` })
  root.append(detailList(rows))
  const note = document.createElement('p')
  note.className = 'cell-popup__note'
  note.textContent =
    "Area forecast at the slider hour, at your load weight. Checkpoint dots show the forecast when the truck reaches them."
  root.append(note)
  return root
}

/** Popup content built from text nodes only (no HTML injection). */
export function checkpointPopupContent(
  routeLabel: string,
  cp: Checkpoint,
  etaFrame: number | null,
  onShowFrame: ((frame: number) => void) | undefined,
): HTMLElement {
  const root = document.createElement('div')
  root.className = 'checkpoint-popup'
  root.style.setProperty('--popup-accent', riskColor(cp.risk?.overall ?? null))
  const title = document.createElement('strong')
  title.className = 'checkpoint-popup__title'
  title.textContent = `${routeLabel} · checkpoint ${cp.index + 1}: ${riskLabel(cp.risk?.overall ?? null)}`
  root.append(title)
  root.append(detailList(checkpointRows(cp)))
  for (const warning of cp.warnings) {
    const p = document.createElement('p')
    p.className = 'checkpoint-popup__warning'
    p.textContent = warning
    root.append(p)
  }
  if (etaFrame !== null && onShowFrame) {
    const button = document.createElement('button')
    button.type = 'button'
    button.className = 'popup-action'
    button.textContent = `Show shading at this ETA (+${etaFrame} h)`
    button.addEventListener('click', () => onShowFrame(etaFrame))
    root.append(button)
  }
  return root
}
