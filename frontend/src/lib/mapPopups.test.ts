// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest'
import { checkpoint, heatmap } from '../test/fixtures'
import { cellPopupContent, checkpointPopupContent } from './mapPopups'

const DEPARTURE = '2026-10-25T13:00:00Z'

describe('corridor cell popup', () => {
  it('states the slider hour and the cell values for that frame', () => {
    const data = heatmap(49, 3)
    data.risk[35][0] = 3
    data.wind_mph[35][0] = 14
    data.snow_in_per_hr[35][0] = 2.4
    const text = cellPopupContent(data, DEPARTURE, 35, 0).textContent ?? ''
    expect(text).toContain('Shading at departure +35 h: Severe')
    expect(text).toContain('14 mph')
    expect(text).toContain('2.40 in/hr')
    expect(text).toContain('Checkpoint dots show the forecast when the truck reaches them')
  })

  it('says unknown, not Low, for a cell without forecast', () => {
    const data = heatmap(49, 3)
    const text = cellPopupContent(data, DEPARTURE, 1, 2).textContent ?? ''
    expect(text).toContain('No forecast')
    expect(text).toContain('Unknown: no forecast for this hour')
  })
})

describe('checkpoint popup', () => {
  it('offers to sync the shading to the checkpoint ETA hour', () => {
    const onShow = vi.fn()
    const root = checkpointPopupContent('Route B', checkpoint({ index: 19 }), 7, onShow)
    const button = root.querySelector('button')!
    expect(button.textContent).toBe('Show shading at this ETA (+7 h)')
    button.click()
    expect(onShow).toHaveBeenCalledWith(7)
  })

  it('has no sync button when the ETA is outside the 48 h overlay', () => {
    expect(checkpointPopupContent('Route B', checkpoint(), null, vi.fn()).querySelector('button')).toBeNull()
  })
})
