import { useEffect, useRef, useState } from 'react'
import { fetchHealth, planTrip } from './api/client'
import type { TripPlanRequest, TripPlanResponse } from './api/types'
import { AppHeader, type BackendStatus } from './components/AppHeader'
import { BaseMap } from './components/BaseMap'
import { ErrorNotice } from './components/ErrorNotice'
import { HeatmapControl } from './components/HeatmapControl'
import { MapEmptyState, MapLoading } from './components/MapStatus'
import { RecommendationPanel } from './components/RecommendationPanel'
import { RouteInsights } from './components/RouteInsights'
import { RouteList } from './components/RouteList'
import { TripForm } from './components/TripForm'
import { useElapsedSeconds } from './hooks/useElapsedSeconds'
import { useMediaQuery } from './hooks/useMediaQuery'
import { describeApiError, type ErrorDescription } from './lib/apiErrors'

const NO_ROUTES: TripPlanResponse['routes'] = []
const WIDE_LAYOUT = '(min-width: 1440px)'

type PlanState =
  | { status: 'idle' }
  | { status: 'loading'; startedAt: number }
  | { status: 'success'; plan: TripPlanResponse }
  | { status: 'error'; error: ErrorDescription }

function App() {
  const [backendStatus, setBackendStatus] = useState<BackendStatus>('checking')
  const [planState, setPlanState] = useState<PlanState>({ status: 'idle' })
  const [selectedRouteId, setSelectedRouteId] = useState<string | null>(null)
  const [selectedCheckpoint, setSelectedCheckpoint] = useState<number | null>(null)
  const [heatmapFrame, setHeatmapFrame] = useState(0)
  const [showHeatmap, setShowHeatmap] = useState(true)
  const planController = useRef<AbortController | null>(null)
  const wide = useMediaQuery(WIDE_LAYOUT)
  const elapsed = useElapsedSeconds(planState.status === 'loading' ? planState.startedAt : null)

  useEffect(() => {
    const controller = new AbortController()
    fetchHealth(controller.signal)
      .then(() => setBackendStatus('online'))
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          console.error(error)
          setBackendStatus('offline')
        }
      })
    return () => controller.abort()
  }, [])

  useEffect(() => () => planController.current?.abort(), [])

  async function handlePlan(request: TripPlanRequest) {
    planController.current?.abort()
    const controller = new AbortController()
    planController.current = controller

    setPlanState({ status: 'loading', startedAt: Date.now() })
    setSelectedRouteId(null)
    setSelectedCheckpoint(null)
    setHeatmapFrame(0)
    try {
      const plan = await planTrip(request, controller.signal)
      setPlanState({ status: 'success', plan })
      setSelectedRouteId(plan.recommendation.route_id ?? plan.routes[0]?.id ?? null)
    } catch (error) {
      if (controller.signal.aborted) return
      setPlanState({ status: 'error', error: describeApiError(error) })
    }
  }

  /** Jump the overlay to a frame and make sure it is visible. */
  function showFrame(frame: number) {
    setHeatmapFrame(frame)
    setShowHeatmap(true)
  }

  function selectRoute(routeId: string) {
    if (routeId !== selectedRouteId) setSelectedCheckpoint(null)
    setSelectedRouteId(routeId)
  }

  const loading = planState.status === 'loading'
  const plan = planState.status === 'success' ? planState.plan : null
  const routes = plan ? plan.routes : NO_ROUTES
  const selectedRoute = routes.find((route) => route.id === selectedRouteId) ?? null
  const insights = selectedRoute && (
    <RouteInsights
      route={selectedRoute}
      selectedCheckpoint={selectedCheckpoint}
      onSelectCheckpoint={setSelectedCheckpoint}
      overlayFrame={heatmapFrame}
      heatmap={plan?.heatmap ?? null}
      onShowFrame={showFrame}
    />
  )

  return (
    <div className="app">
      <AppHeader backendStatus={backendStatus} weather={plan?.weather_risk ?? null} />
      <main className={plan && wide ? 'workspace workspace--three' : 'workspace'}>
        <aside className="sidebar">
          <div className="sidebar__planner">
            <TripForm loading={loading} onSubmit={handlePlan} />
          </div>
          <div className="sidebar__results">
            {planState.status === 'error' && <ErrorNotice error={planState.error} />}
            {plan && plan.routes.length === 0 && (
              <p className="notice notice--info">No routes were returned for this trip.</p>
            )}
            {plan && plan.routes.length > 0 && (
              <>
                <RecommendationPanel recommendation={plan.recommendation} routes={plan.routes} />
                <RouteList plan={plan} selectedRouteId={selectedRouteId} onSelect={selectRoute} />
                {!wide && insights}
              </>
            )}
          </div>
        </aside>

        <section className="map-panel" aria-label="Map">
          <BaseMap
            routes={routes}
            selectedRouteId={selectedRouteId}
            onSelectRoute={selectRoute}
            heatmap={plan?.heatmap ?? null}
            heatmapFrame={heatmapFrame}
            showHeatmap={showHeatmap}
            selectedCheckpoint={selectedCheckpoint}
            onSelectCheckpoint={setSelectedCheckpoint}
            departureTime={plan?.inputs.departure_time ?? null}
            onShowFrame={showFrame}
          />
          {planState.status === 'idle' && <MapEmptyState />}
          {loading && <MapLoading seconds={elapsed} />}
          {plan && (
            <HeatmapControl
              heatmap={plan.heatmap}
              departureTime={plan.inputs.departure_time}
              frame={heatmapFrame}
              onFrameChange={setHeatmapFrame}
              visible={showHeatmap}
              onVisibleChange={setShowHeatmap}
            />
          )}
        </section>

        {plan && wide && <aside className="insights">{insights}</aside>}
      </main>
    </div>
  )
}

export default App
