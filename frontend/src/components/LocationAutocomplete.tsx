import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react'
import { ApiError, geocode } from '../api/client'
import type { Place } from '../api/types'

const MIN_QUERY_LENGTH = 2
const DEBOUNCE_MS = 300

interface Props {
  label: string
  placeholder?: string
  value: Place | null
  onChange: (place: Place | null) => void
  disabled?: boolean
}

type SearchState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'done'; results: Place[] }
  | { status: 'error'; message: string }

export function LocationAutocomplete({ label, placeholder, value, onChange, disabled }: Props) {
  const inputId = useId()
  const listId = `${inputId}-list`
  const [text, setText] = useState(value?.label ?? '')
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState<SearchState>({ status: 'idle' })
  const [activeIndex, setActiveIndex] = useState(-1)
  const blurTimer = useRef<number | undefined>(undefined)

  const query = text.trim()
  // Search only while the user is typing, not after a suggestion is selected.
  const searching = open && query.length >= MIN_QUERY_LENGTH && query !== value?.label

  // Debounced lookup.
  useEffect(() => {
    if (!searching) return
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      setSearch({ status: 'loading' })
      geocode(query, controller.signal)
        .then((results) => {
          setSearch({ status: 'done', results })
          setActiveIndex(results.length ? 0 : -1)
        })
        .catch((error: unknown) => {
          if (controller.signal.aborted) return
          const message = error instanceof ApiError ? error.message : 'Location search failed.'
          setSearch({ status: 'error', message })
        })
    }, DEBOUNCE_MS)
    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [query, searching])

  useEffect(() => () => window.clearTimeout(blurTimer.current), [])

  const visible: SearchState = searching ? search : { status: 'idle' }
  const results = visible.status === 'done' ? visible.results : []

  function select(place: Place) {
    setText(place.label)
    setOpen(false)
    setSearch({ status: 'idle' })
    onChange(place)
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (!open || results.length === 0) return
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setActiveIndex((i) => (i + 1) % results.length)
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActiveIndex((i) => (i <= 0 ? results.length - 1 : i - 1))
    } else if (event.key === 'Enter' && activeIndex >= 0) {
      event.preventDefault()
      select(results[activeIndex])
    } else if (event.key === 'Escape') {
      setOpen(false)
    }
  }

  const showList = visible.status !== 'idle'

  return (
    <div className="field autocomplete">
      <label htmlFor={inputId}>{label}</label>
      <input
        id={inputId}
        type="text"
        role="combobox"
        aria-expanded={showList}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={showList && activeIndex >= 0 ? `${listId}-${activeIndex}` : undefined}
        autoComplete="off"
        placeholder={placeholder}
        value={text}
        disabled={disabled}
        onChange={(event) => {
          setText(event.target.value)
          setOpen(true)
          if (value) onChange(null) // edited text no longer matches the selection
        }}
        onFocus={() => setOpen(true)}
        // Delay so a click on a suggestion registers before the list closes.
        onBlur={() => {
          blurTimer.current = window.setTimeout(() => setOpen(false), 150)
        }}
        onKeyDown={handleKeyDown}
      />
      {showList && (
        <ul id={listId} role="listbox" className="autocomplete-list">
          {visible.status === 'loading' && <li className="autocomplete-note">Searching…</li>}
          {visible.status === 'error' && (
            <li className="autocomplete-note autocomplete-note--error">{visible.message}</li>
          )}
          {visible.status === 'done' && results.length === 0 && (
            <li className="autocomplete-note">No matching locations</li>
          )}
          {results.map((place, index) => (
            <li
              key={place.id}
              id={`${listId}-${index}`}
              role="option"
              aria-selected={index === activeIndex}
              className={index === activeIndex ? 'autocomplete-option is-active' : 'autocomplete-option'}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => select(place)}
              onMouseEnter={() => setActiveIndex(index)}
            >
              <span>{place.label}</span>
              <span className="autocomplete-kind">{place.kind}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
