import type { WeatherRiskStatus } from '../api/types'
import { Icon } from './Icon'

export type BackendStatus = 'checking' | 'online' | 'offline'

const BACKEND_TEXT: Record<BackendStatus, string> = {
  checking: 'API: checking',
  online: 'API: online',
  offline: 'API: offline',
}

const WEATHER_TEXT: Record<WeatherRiskStatus['status'], string> = {
  complete: 'Forecasts complete',
  partial: 'Forecasts partial',
  unavailable: 'Forecasts unavailable',
}

interface Props {
  backendStatus: BackendStatus
  weather: WeatherRiskStatus | null
}

export function AppHeader({ backendStatus, weather }: Props) {
  return (
    <header className="app-header">
      <div className="brand">
        <span className="brand__mark" aria-hidden>
          <Icon name="truck" size={20} />
        </span>
        <div>
          <h1 className="brand__title">Weather-Aware Truck Routing</h1>
          <p className="brand__subtitle">Forecast-based route risk for loaded trucks</p>
        </div>
      </div>
      <div className="header-status" aria-label="Service status">
        {weather && (
          <span
            className={`status-pill status-pill--${weather.status === 'complete' ? 'ok' : weather.status === 'partial' ? 'warn' : 'bad'}`}
            title={weather.message}
          >
            <Icon name="signal" size={14} />
            {WEATHER_TEXT[weather.status]} · {weather.checkpoints_with_forecast}/{weather.checkpoints_total}
          </span>
        )}
        <span className="status-pill status-pill--muted">
          <Icon name="layers" size={14} />
          TomTom · Open-Meteo
        </span>
        <span className={`status-pill status-pill--${backendStatus === 'online' ? 'ok' : backendStatus === 'offline' ? 'bad' : 'muted'}`}>
          <span className="status-dot" aria-hidden />
          {BACKEND_TEXT[backendStatus]}
        </span>
      </div>
    </header>
  )
}
