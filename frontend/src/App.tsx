import { useEffect, useRef, useState } from 'react'
import { ApiError, fetchHealth, planTrip } from './api/client'
import type { TripPlanRequest, TripPlanResponse } from './api/types'
import { BaseMap } from './components/BaseMap'
import { CheckpointList } from './components/CheckpointList'
import { HeatmapControl } from './components/HeatmapControl'
import { RecommendationPanel } from './components/RecommendationPanel'
import { RouteList } from './components/RouteList'
import { TripForm } from './components/TripForm'

type BackendStatus = 'checking' | 'online' | 'offline'

const NO_ROUTES: TripPlanResponse['routes'] = []

type PlanState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'success'; plan: TripPlanResponse }
  | { status: 'error'; message: string }

function App() {
  const [backendStatus, setBackendStatus] = useState<BackendStatus>('checking')
  const [planState, setPlanState] = useState<PlanState>({ status: 'idle' })
  const [selectedRouteId, setSelectedRouteId] = useState<string | null>(null)
  const [selectedCheckpoint, setSelectedCheckpoint] = useState<number | null>(null)
  const [heatmapFrame, setHeatmapFrame] = useState(0)
  const [showHeatmap, setShowHeatmap] = useState(true)
  const planController = useRef<AbortController | null>(null)

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

    setPlanState({ status: 'loading' })
    setSelectedRouteId(null)
    setSelectedCheckpoint(null)
    setHeatmapFrame(0)
    try {
      const plan = await planTrip(request, controller.signal)
      setPlanState({ status: 'success', plan })
      setSelectedRouteId(plan.recommendation.route_id ?? plan.routes[0]?.id ?? null)
    } catch (error) {
      if (controller.signal.aborted) return
      const message = error instanceof ApiError ? error.message : 'Something went wrong while generating routes.'
      setPlanState({ status: 'error', message })
    }
  }

  function selectRoute(routeId: string) {
    if (routeId !== selectedRouteId) setSelectedCheckpoint(null)
    setSelectedRouteId(routeId)
  }

  const plan = planState.status === 'success' ? planState.plan : null
  const routes = plan ? plan.routes : NO_ROUTES
  const selectedRoute = routes.find((route) => route.id === selectedRouteId) ?? null

  return (
    <div className="app">
      <header className="app-header">
        <h1>Weather-Aware Truck Routing</h1>
        <span className={`status status--${backendStatus}`}>API: {backendStatus}</span>
      </header>
      <main className="app-main">
        <aside className="sidebar">
          <TripForm loading={planState.status === 'loading'} onSubmit={handlePlan} />

          {planState.status === 'idle' && (
            <p className="message message--muted">
              Choose an origin and destination, then generate routes to compare weather risk on the map.
            </p>
          )}
          {planState.status === 'loading' && (
            <p className="message message--muted" role="status">
              Requesting truck routes and checkpoint forecasts…
            </p>
          )}
          {planState.status === 'error' && (
            <p className="message message--error" role="alert">
              {planState.message}
            </p>
          )}
          {plan && plan.routes.length === 0 && (
            <p className="message message--info">No routes were returned for this trip.</p>
          )}
          {plan && plan.routes.length > 0 && (
            <>
              <RecommendationPanel recommendation={plan.recommendation} routes={plan.routes} />
              <RouteList plan={plan} selectedRouteId={selectedRouteId} onSelect={selectRoute} />
              {selectedRoute && (
                <CheckpointList
                  route={selectedRoute}
                  selectedIndex={selectedCheckpoint}
                  onSelect={setSelectedCheckpoint}
                />
              )}
            </>
          )}
        </aside>
        <section className="map-panel">
          <BaseMap
            routes={routes}
            selectedRouteId={selectedRouteId}
            onSelectRoute={selectRoute}
            heatmap={plan?.heatmap ?? null}
            heatmapFrame={heatmapFrame}
            showHeatmap={showHeatmap}
            selectedCheckpoint={selectedCheckpoint}
            onSelectCheckpoint={setSelectedCheckpoint}
          />
          {plan && (
            <HeatmapControl
              heatmap={plan.heatmap}
              frame={heatmapFrame}
              onFrameChange={setHeatmapFrame}
              visible={showHeatmap}
              onVisibleChange={setShowHeatmap}
            />
          )}
        </section>
      </main>
    </div>
  )
}

export default App
