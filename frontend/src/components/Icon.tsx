// Small inline stroke-icon set (24 x 24 grid, drawn for this app) so no icon
// library dependency is needed. Icons are decorative unless given a `title`.

const PATHS = {
  truck: 'M2 6h12v10H2z M14 10h4.5L22 13.5V16h-8 M6.5 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4z M17.5 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4z',
  route: 'M6 21a2 2 0 1 0 0-4 2 2 0 0 0 0 4z M18 7a2 2 0 1 0 0-4 2 2 0 0 0 0 4z M8 19h8.5a3.5 3.5 0 0 0 0-7h-9a3.5 3.5 0 0 1 0-7H16',
  pin: 'M12 21s-7-6.2-7-11.5a7 7 0 1 1 14 0C19 14.8 12 21 12 21z M12 12a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5z',
  flag: 'M5 21V4 M5 4h12l-2.5 4L17 12H5',
  clock: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M12 7v5l3 2',
  calendar: 'M4 6h16v14H4z M4 10h16 M8 3v4 M16 3v4',
  weight: 'M5 9h14l2 11H3z M9 9a3 3 0 0 1 6 0',
  wind: 'M3 8h10a3 3 0 1 0-3-3 M3 12h15a3 3 0 1 1-3 3 M3 16h7',
  rain: 'M7 15a4 4 0 0 1-.6-7.96A6 6 0 0 1 17.7 8 3.5 3.5 0 0 1 17.5 15z M8 18l-1 3 M12 18l-1 3 M16 18l-1 3',
  snow: 'M12 3v18 M4.2 7.5l15.6 9 M19.8 7.5l-15.6 9 M9.5 4.5 12 6l2.5-1.5 M9.5 19.5 12 18l2.5 1.5',
  gauge: 'M4 18a8.5 8.5 0 1 1 16 0 M12 14l4.5-4.5 M12 14.5a1 1 0 1 0 0-.1',
  alert: 'M12 3.5 22 20.5H2z M12 10v5 M12 17.6v.4',
  check: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M8 12.5l2.8 2.8L16.5 9',
  layers: 'M12 3l9 5-9 5-9-5z M3 13l9 5 9-5',
  info: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M12 11v6 M12 7.6v.4',
  shield: 'M12 3l8 3v5.5c0 4.6-3.3 8.3-8 9.5-4.7-1.2-8-4.9-8-9.5V6z',
  signal: 'M4 18v-3 M9 18v-6 M14 18V9 M19 18V5',
  search: 'M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14z M16.5 16.5 21 21',
  close: 'M6 6l12 12 M18 6 6 18',
} as const

export type IconName = keyof typeof PATHS

interface Props {
  name: IconName
  size?: number
  title?: string
  className?: string
}

export function Icon({ name, size = 18, title, className }: Props) {
  return (
    <svg
      className={className ? `icon ${className}` : 'icon'}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.9}
      strokeLinecap="round"
      strokeLinejoin="round"
      role={title ? 'img' : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title}
    >
      <path d={PATHS[name]} />
    </svg>
  )
}
