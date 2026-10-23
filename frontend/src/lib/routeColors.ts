// Route identity colours. Deliberately avoid green/yellow/red, which are
// reserved for risk levels in later phases.
export const ROUTE_COLORS = ['#2563eb', '#9333ea', '#0e7490'] as const

export function routeColor(index: number): string {
  return ROUTE_COLORS[index % ROUTE_COLORS.length]
}
