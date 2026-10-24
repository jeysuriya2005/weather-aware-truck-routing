import { useEffect, useRef, useState } from 'react'
import {
  LngLatBounds,
  MapLibreMap,
  NavigationControl,
  Popup,
  ScaleControl,
  setWorkerUrl,
  type GeoJSONSource,
} from 'maplibre-gl'
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { FeatureCollection, LineString, Point } from 'geojson'
import type { Checkpoint, Heatmap, RouteOption } from '../api/types'
import { INITIAL_VIEW, MAP_STYLE_URL } from '../config'
import {
  frameForForecastHour,
  heatmapColorExpression,
  heatmapFeatures,
  heatmapOpacityExpression,
  heatmapRadiusExpression,
  meanLatitude,
  riskColorMatch,
} from '../lib/heatmap'
import { cellPopupContent, checkpointPopupContent } from '../lib/mapPopups'
import { routeColor } from '../lib/routeColors'

// MapLibre v6 loads its worker from a file next to its own module. Vite
// relocates the library (pre-bundling in dev, hashing in builds) without that
// file, so tiles and GeoJSON never get parsed. Point it at a Vite-managed copy.
setWorkerUrl(maplibreWorkerUrl)

const ROUTES_SOURCE = 'routes'
const ROUTES_CASING_LAYER = 'routes-casing'
const ROUTES_LINE_LAYER = 'routes-line'
const ROUTES_SELECTED_LAYER = 'routes-selected'
const ROUTES_SELECTED_CASING_LAYER = 'routes-selected-casing'
const HEATMAP_SOURCE = 'heatmap'
const HEATMAP_LAYER = 'heatmap-cells'
const CHECKPOINTS_SOURCE = 'checkpoints'
const CHECKPOINTS_LAYER = 'checkpoints'
const CHECKPOINTS_SELECTED_LAYER = 'checkpoints-selected'

const EMPTY: FeatureCollection = { type: 'FeatureCollection', features: [] }

const CHECKPOINT_COLOR = riskColorMatch(['get', 'risk'], 'code')

interface Props {
  routes?: RouteOption[]
  selectedRouteId?: string | null
  onSelectRoute?: (routeId: string) => void
  heatmap?: Heatmap | null
  heatmapFrame?: number
  showHeatmap?: boolean
  selectedCheckpoint?: number | null
  onSelectCheckpoint?: (index: number | null) => void
  /** Requested departure (ISO); overlay frame N = departure + N hours. */
  departureTime?: string | null
  /** Move the overlay slider (used by "show shading at this checkpoint's ETA"). */
  onShowFrame?: (frame: number) => void
}

function toFeatureCollection(routes: RouteOption[]): FeatureCollection<LineString> {
  return {
    type: 'FeatureCollection',
    features: routes.map((route) => ({
      type: 'Feature',
      properties: { id: route.id, color: routeColor(route.index) },
      geometry: route.geometry,
    })),
  }
}

function checkpointFeatures(checkpoints: Checkpoint[]): FeatureCollection<Point> {
  return {
    type: 'FeatureCollection',
    features: checkpoints.map((cp) => ({
      type: 'Feature',
      properties: { index: cp.index, risk: cp.risk?.overall ?? 'unknown' },
      geometry: { type: 'Point', coordinates: [cp.lon, cp.lat] },
    })),
  }
}

export function BaseMap({
  routes = [],
  selectedRouteId = null,
  onSelectRoute,
  heatmap = null,
  heatmapFrame = 0,
  showHeatmap = true,
  selectedCheckpoint = null,
  onSelectCheckpoint,
  departureTime = null,
  onShowFrame,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const popupRef = useRef<Popup | null>(null)
  const cellPopupRef = useRef<{ popup: Popup; index: number } | null>(null)
  const onSelectRef = useRef(onSelectRoute)
  const onSelectCheckpointRef = useRef(onSelectCheckpoint)
  const onShowFrameRef = useRef(onShowFrame)
  // Latest overlay state for map event handlers registered once at load.
  const overlayRef = useRef({ heatmap, frame: heatmapFrame, departureTime })
  const [ready, setReady] = useState(false)

  useEffect(() => {
    onSelectRef.current = onSelectRoute
    onSelectCheckpointRef.current = onSelectCheckpoint
    onShowFrameRef.current = onShowFrame
  }, [onSelectRoute, onSelectCheckpoint, onShowFrame])

  useEffect(() => {
    overlayRef.current = { heatmap, frame: heatmapFrame, departureTime }
  }, [heatmap, heatmapFrame, departureTime])

  // Create the map once.
  useEffect(() => {
    if (!containerRef.current) return

    const map = new MapLibreMap({
      container: containerRef.current,
      style: MAP_STYLE_URL,
      center: INITIAL_VIEW.center,
      zoom: INITIAL_VIEW.zoom,
    })
    map.addControl(new NavigationControl({ showCompass: false }), 'top-right')
    map.addControl(new ScaleControl({ unit: 'imperial' }), 'bottom-left')

    map.on('load', () => {
      // Heatmap first so it sits beneath the routes.
      map.addSource(HEATMAP_SOURCE, { type: 'geojson', data: EMPTY })
      map.addLayer({
        id: HEATMAP_LAYER,
        type: 'circle',
        source: HEATMAP_SOURCE,
        paint: {
          'circle-color': heatmapColorExpression(0),
          'circle-opacity': heatmapOpacityExpression(0),
          'circle-radius': 8,
          'circle-blur': 0.55,
        },
      })

      map.addSource(ROUTES_SOURCE, { type: 'geojson', data: toFeatureCollection([]) })
      map.addLayer({
        id: ROUTES_CASING_LAYER,
        type: 'line',
        source: ROUTES_SOURCE,
        layout: { 'line-join': 'round', 'line-cap': 'round' },
        paint: { 'line-color': '#ffffff', 'line-width': 7, 'line-opacity': 0.85 },
      })
      map.addLayer({
        id: ROUTES_LINE_LAYER,
        type: 'line',
        source: ROUTES_SOURCE,
        layout: { 'line-join': 'round', 'line-cap': 'round' },
        paint: { 'line-color': ['get', 'color'], 'line-width': 4, 'line-opacity': 0.6 },
      })
      // The selected route is redrawn on top: a wide white halo, then the line itself.
      map.addLayer({
        id: ROUTES_SELECTED_CASING_LAYER,
        type: 'line',
        source: ROUTES_SOURCE,
        filter: ['==', ['get', 'id'], ''],
        layout: { 'line-join': 'round', 'line-cap': 'round' },
        paint: { 'line-color': '#ffffff', 'line-width': 11, 'line-opacity': 0.95 },
      })
      map.addLayer({
        id: ROUTES_SELECTED_LAYER,
        type: 'line',
        source: ROUTES_SOURCE,
        filter: ['==', ['get', 'id'], ''],
        layout: { 'line-join': 'round', 'line-cap': 'round' },
        paint: { 'line-color': ['get', 'color'], 'line-width': 6.5, 'line-opacity': 1 },
      })

      map.addSource(CHECKPOINTS_SOURCE, { type: 'geojson', data: EMPTY })
      map.addLayer({
        id: CHECKPOINTS_LAYER,
        type: 'circle',
        source: CHECKPOINTS_SOURCE,
        paint: {
          'circle-color': CHECKPOINT_COLOR,
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 4, 4.5, 9, 8],
          'circle-stroke-color': '#ffffff',
          'circle-stroke-width': 2,
        },
      })
      map.addLayer({
        id: CHECKPOINTS_SELECTED_LAYER,
        type: 'circle',
        source: CHECKPOINTS_SOURCE,
        filter: ['==', ['get', 'index'], -1],
        paint: {
          'circle-color': CHECKPOINT_COLOR,
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 4, 8, 9, 12],
          'circle-stroke-color': '#0f172a',
          'circle-stroke-width': 3,
        },
      })

      for (const layer of [ROUTES_LINE_LAYER, ROUTES_SELECTED_LAYER]) {
        map.on('click', layer, (event) => {
          // Checkpoint clicks take precedence over the route underneath.
          if (map.queryRenderedFeatures(event.point, { layers: [CHECKPOINTS_LAYER] }).length) return
          const id = event.features?.[0]?.properties?.id
          if (typeof id === 'string') onSelectRef.current?.(id)
        })
      }
      map.on('click', CHECKPOINTS_LAYER, (event) => {
        const index = event.features?.[0]?.properties?.index
        if (typeof index === 'number') onSelectCheckpointRef.current?.(index)
      })
      // Clicking shaded corridor (not a route or checkpoint) shows that cell's forecast.
      map.on('click', HEATMAP_LAYER, (event) => {
        const above = map.queryRenderedFeatures(event.point, {
          layers: [CHECKPOINTS_LAYER, ROUTES_LINE_LAYER, ROUTES_SELECTED_LAYER],
        })
        const index = event.features?.[0]?.properties?.i
        const { heatmap: data, frame, departureTime: departure } = overlayRef.current
        if (above.length || typeof index !== 'number' || !data || !departure) return
        cellPopupRef.current?.popup.remove()
        // One map popup at a time: closing the checkpoint popup also clears the selection.
        popupRef.current?.remove()
        const popup = new Popup({ maxWidth: '300px', offset: 8 })
          .setLngLat(event.lngLat)
          .setDOMContent(cellPopupContent(data, departure, frame, index))
          .addTo(map)
        popup.on('close', () => {
          if (cellPopupRef.current?.popup === popup) cellPopupRef.current = null
        })
        cellPopupRef.current = { popup, index }
      })
      map.on('mouseenter', HEATMAP_LAYER, () => (map.getCanvas().style.cursor = 'help'))
      map.on('mouseleave', HEATMAP_LAYER, () => (map.getCanvas().style.cursor = ''))
      for (const layer of [ROUTES_LINE_LAYER, ROUTES_SELECTED_LAYER, CHECKPOINTS_LAYER]) {
        map.on('mouseenter', layer, () => (map.getCanvas().style.cursor = 'pointer'))
        map.on('mouseleave', layer, () => (map.getCanvas().style.cursor = ''))
      }
      setReady(true)
    })

    mapRef.current = map
    return () => {
      popupRef.current?.remove()
      mapRef.current = null
      map.remove()
    }
  }, [])

  // Update route data and fit the view when a new set of routes arrives.
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    const source = map.getSource(ROUTES_SOURCE) as GeoJSONSource | undefined
    source?.setData(toFeatureCollection(routes))

    if (routes.length === 0) return
    const bounds = new LngLatBounds()
    for (const route of routes) {
      for (const coordinate of route.geometry.coordinates) bounds.extend(coordinate)
    }
    // The layout can change in the same render (e.g. the route-weather column
    // appears), and MapLibre only learns the new container size asynchronously.
    // Resize first so the fit uses the real width; otherwise routes get cut off.
    map.resize()
    map.fitBounds(bounds, { padding: 60, duration: 600 })
  }, [ready, routes])

  // Highlight the selected route without touching the data.
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    for (const layer of [ROUTES_SELECTED_CASING_LAYER, ROUTES_SELECTED_LAYER]) {
      map.setFilter(layer, ['==', ['get', 'id'], selectedRouteId ?? ''])
    }
  }, [ready, selectedRouteId])

  // Heatmap data: uploaded once per plan.
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    const source = map.getSource(HEATMAP_SOURCE) as GeoJSONSource | undefined
    source?.setData(heatmap ? heatmapFeatures(heatmap) : EMPTY)
    if (heatmap) {
      map.setPaintProperty(HEATMAP_LAYER, 'circle-radius',
        heatmapRadiusExpression(heatmap.spacing_degrees, meanLatitude(heatmap)))
    }
  }, [ready, heatmap])

  // Slider: swap the style expression only.
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    map.setPaintProperty(HEATMAP_LAYER, 'circle-color', heatmapColorExpression(heatmapFrame))
    map.setPaintProperty(HEATMAP_LAYER, 'circle-opacity', heatmapOpacityExpression(heatmapFrame))
    // An open cell popup follows the slider, so it always describes the visible shading.
    const open = cellPopupRef.current
    if (open && heatmap && departureTime) {
      open.popup.setDOMContent(cellPopupContent(heatmap, departureTime, heatmapFrame, open.index))
    }
  }, [ready, heatmapFrame, heatmap, departureTime])

  // A new plan invalidates any open cell popup.
  useEffect(() => {
    const open = cellPopupRef.current
    cellPopupRef.current = null
    open?.popup.remove()
  }, [heatmap])

  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    map.setLayoutProperty(HEATMAP_LAYER, 'visibility', showHeatmap && heatmap ? 'visible' : 'none')
  }, [ready, showHeatmap, heatmap])

  const selectedRoute = routes.find((route) => route.id === selectedRouteId) ?? null

  // Checkpoints of the selected route.
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    const source = map.getSource(CHECKPOINTS_SOURCE) as GeoJSONSource | undefined
    source?.setData(selectedRoute ? checkpointFeatures(selectedRoute.checkpoints) : EMPTY)
  }, [ready, selectedRoute])

  // Selected checkpoint: highlight, popup, and pan into view if needed.
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    map.setFilter(CHECKPOINTS_SELECTED_LAYER, ['==', ['get', 'index'], selectedCheckpoint ?? -1])
    // Detach before removing, so the old popup's close handler can't clear the new selection.
    const previous = popupRef.current
    popupRef.current = null
    previous?.remove()

    const cp = selectedRoute?.checkpoints.find((c) => c.index === selectedCheckpoint)
    if (!selectedRoute || !cp) return
    // One map popup at a time: a checkpoint popup replaces any open cell popup.
    const cell = cellPopupRef.current
    cellPopupRef.current = null
    cell?.popup.remove()
    const popup = new Popup({ maxWidth: '320px', offset: 12 })
      .setLngLat([cp.lon, cp.lat])
      .setDOMContent(
        checkpointPopupContent(
          selectedRoute.label,
          cp,
          heatmap ? frameForForecastHour(heatmap, cp.forecast_time) : null,
          (frame) => onShowFrameRef.current?.(frame),
        ),
      )
      .addTo(map)
    popup.on('close', () => {
      if (popupRef.current === popup) onSelectCheckpointRef.current?.(null)
    })
    popupRef.current = popup
    if (!map.getBounds().contains([cp.lon, cp.lat])) map.panTo([cp.lon, cp.lat])
  }, [ready, selectedRoute, selectedCheckpoint, heatmap])

  // data-map-ready lets browser tests wait for the style/layers before interacting.
  return <div ref={containerRef} className="map" aria-label="Route map" data-map-ready={ready} />
}
