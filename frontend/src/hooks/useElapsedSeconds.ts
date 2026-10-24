import { useEffect, useState } from 'react'

/**
 * Whole seconds elapsed since `startedAt` (epoch ms), ticking once a second
 * while `startedAt` is set. Real elapsed time, not a fake progress value.
 */
export function useElapsedSeconds(startedAt: number | null): number {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    if (startedAt === null) return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [startedAt])

  return startedAt === null ? 0 : Math.max(0, Math.floor((now - startedAt) / 1000))
}
