import { useState, type FormEvent } from 'react'
import type { CheckpointIntervalMiles, Place, TripPlanRequest } from '../api/types'
import { defaultDeparture, departureBounds, departureProblem, localInputToIso, toLocalInputValue } from '../lib/datetime'
import { Icon } from './Icon'
import { LocationAutocomplete } from './LocationAutocomplete'

const INTERVALS: CheckpointIntervalMiles[] = [10, 25, 50]
const DEFAULT_INTERVAL: CheckpointIntervalMiles = 25
const MAX_LOAD_WEIGHT_LB = 200_000 // mirrors the backend sanity bound

interface Props {
  loading: boolean
  onSubmit: (request: TripPlanRequest) => void
}

export function TripForm({ loading, onSubmit }: Props) {
  const [origin, setOrigin] = useState<Place | null>(null)
  const [destination, setDestination] = useState<Place | null>(null)
  const [departure, setDeparture] = useState(() => toLocalInputValue(defaultDeparture()))
  const [loadWeight, setLoadWeight] = useState('')
  const [intervalMiles, setIntervalMiles] = useState<CheckpointIntervalMiles>(DEFAULT_INTERVAL)
  const [formError, setFormError] = useState<string | null>(null)
  const [bounds, setBounds] = useState(() => departureBounds())

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBounds(departureBounds())
    const departureIso = localInputToIso(departure)
    const load = Number(loadWeight)

    let error: string | null = null
    if (!origin) error = 'Choose an origin from the suggestions.'
    else if (!destination) error = 'Choose a destination from the suggestions.'
    else if (origin.id === destination.id) error = 'Origin and destination must be different.'
    else if (!departureIso) error = 'Enter a valid departure date and time.'
    else if (departureProblem(departureIso)) error = departureProblem(departureIso)
    else if (loadWeight.trim() === '' || !Number.isFinite(load) || load < 0 || load > MAX_LOAD_WEIGHT_LB)
      error = `Enter a load weight between 0 and ${MAX_LOAD_WEIGHT_LB.toLocaleString('en-US')} lb.`

    setFormError(error)
    if (error || !origin || !destination || !departureIso) return

    onSubmit({
      origin: { lat: origin.lat, lon: origin.lon, label: origin.label },
      destination: { lat: destination.lat, lon: destination.lon, label: destination.label },
      departure_time: departureIso,
      load_weight_lb: load,
      checkpoint_interval_miles: intervalMiles,
    })
  }

  return (
    <form className="card planner" onSubmit={handleSubmit} noValidate aria-label="Plan a trip">
      <div className="card__header">
        <span className="card__icon">
          <Icon name="route" />
        </span>
        <div>
          <h2 className="card__title">Plan a trip</h2>
          <p className="card__subtitle">Compare truck routes by forecast weather risk</p>
        </div>
      </div>

      <div className="planner__stops">
        <LocationAutocomplete
          label="Origin"
          icon="pin"
          placeholder="City or address, e.g. Dallas, TX"
          value={origin}
          onChange={setOrigin}
          disabled={loading}
        />
        <LocationAutocomplete
          label="Destination"
          icon="flag"
          placeholder="City or address, e.g. Denver, CO"
          value={destination}
          onChange={setDestination}
          disabled={loading}
        />
      </div>

      <div className="field">
        <label htmlFor="departure">Departure (your local time)</label>
        <div className="input-with-icon">
          <Icon name="calendar" className="input-with-icon__icon" />
          <input
            id="departure"
            type="datetime-local"
            value={departure}
            min={bounds.min}
            max={bounds.max}
            onChange={(event) => setDeparture(event.target.value)}
            disabled={loading}
            required
          />
        </div>
        <span className="field__hint">Up to 13 days ahead (forecast range)</span>
      </div>

      <div className="field-row">
        <div className="field">
          <label htmlFor="load-weight">Load weight (lb)</label>
          <div className="input-with-icon">
            <Icon name="weight" className="input-with-icon__icon" />
            <input
              id="load-weight"
              type="number"
              inputMode="numeric"
              min={0}
              max={MAX_LOAD_WEIGHT_LB}
              step={100}
              placeholder="38000"
              value={loadWeight}
              onChange={(event) => setLoadWeight(event.target.value)}
              disabled={loading}
              required
            />
          </div>
        </div>
        <div className="field">
          <label htmlFor="interval">Weather checkpoints</label>
          <select
            id="interval"
            value={intervalMiles}
            onChange={(event) => setIntervalMiles(Number(event.target.value) as CheckpointIntervalMiles)}
            disabled={loading}
          >
            {INTERVALS.map((miles) => (
              <option key={miles} value={miles}>
                Every {miles} mi
              </option>
            ))}
          </select>
        </div>
      </div>

      {formError && (
        <p className="notice notice--error notice--compact" role="alert">
          <Icon name="alert" />
          <span>{formError}</span>
        </p>
      )}

      <button type="submit" className="button-primary" disabled={loading}>
        {loading ? <span className="spinner" aria-hidden /> : <Icon name="route" />}
        {loading ? 'Generating routes…' : 'Generate Routes'}
      </button>
    </form>
  )
}
