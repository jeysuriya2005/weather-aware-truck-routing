import { useState, type FormEvent } from 'react'
import type { CheckpointIntervalMiles, Place, TripPlanRequest } from '../api/types'
import { defaultDeparture, localInputToIso, toLocalInputValue } from '../lib/datetime'
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

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const departureIso = localInputToIso(departure)
    const load = Number(loadWeight)

    let error: string | null = null
    if (!origin) error = 'Choose an origin from the suggestions.'
    else if (!destination) error = 'Choose a destination from the suggestions.'
    else if (origin.id === destination.id) error = 'Origin and destination must be different.'
    else if (!departureIso) error = 'Enter a valid departure date and time.'
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
    <form className="trip-form" onSubmit={handleSubmit} noValidate>
      <LocationAutocomplete
        label="Origin"
        placeholder="e.g. Dallas, TX"
        value={origin}
        onChange={setOrigin}
        disabled={loading}
      />
      <LocationAutocomplete
        label="Destination"
        placeholder="e.g. Denver, CO"
        value={destination}
        onChange={setDestination}
        disabled={loading}
      />

      <div className="field">
        <label htmlFor="departure">Departure (your local time)</label>
        <input
          id="departure"
          type="datetime-local"
          value={departure}
          onChange={(event) => setDeparture(event.target.value)}
          disabled={loading}
          required
        />
      </div>

      <div className="field-row">
        <div className="field">
          <label htmlFor="load-weight">Load weight (lb)</label>
          <input
            id="load-weight"
            type="number"
            inputMode="numeric"
            min={0}
            max={MAX_LOAD_WEIGHT_LB}
            step={100}
            placeholder="e.g. 38000"
            value={loadWeight}
            onChange={(event) => setLoadWeight(event.target.value)}
            disabled={loading}
            required
          />
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
        <p className="message message--error" role="alert">
          {formError}
        </p>
      )}

      <button type="submit" className="button-primary" disabled={loading}>
        {loading ? 'Generating routes…' : 'Generate Routes'}
      </button>
    </form>
  )
}
