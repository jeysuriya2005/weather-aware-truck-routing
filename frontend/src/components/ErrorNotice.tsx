import type { ErrorDescription } from '../lib/apiErrors'
import { Icon } from './Icon'

export function ErrorNotice({ error }: { error: ErrorDescription }) {
  return (
    <div className="notice notice--error" role="alert">
      <Icon name="alert" />
      <div>
        <strong className="notice__title">{error.title}</strong>
        {error.details.length === 1 ? (
          <p>{error.details[0]}</p>
        ) : (
          <ul>
            {error.details.map((detail) => (
              <li key={detail}>{detail}</li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
