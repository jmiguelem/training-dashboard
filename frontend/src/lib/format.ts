/** Parse Whoop ISO (Z) and Garmin "YYYY-MM-DD HH:MM:SS" (GMT) timestamps. */
export function parseTs(s: string): Date {
  if (/Z$|[+-]\d\d:?\d\d$/.test(s)) return new Date(s)
  return new Date(s.replace(' ', 'T') + 'Z')
}

export const dayKey = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

export function weekStart(d: Date): Date {
  const x = new Date(d.getFullYear(), d.getMonth(), d.getDate())
  const dow = (x.getDay() + 6) % 7 // Monday = 0
  x.setDate(x.getDate() - dow)
  return x
}

export const shortDate = (s: string | Date) =>
  (typeof s === 'string' ? parseTs(s) : s).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
  })

export const hours = (ms: number | null | undefined) => (ms ?? 0) / 3_600_000

export function fmtDuration(totalSeconds: number | null): string {
  if (totalSeconds == null) return '-'
  const m = Math.round(totalSeconds / 60)
  const h = Math.floor(m / 60)
  return h > 0 ? `${h}h ${String(m % 60).padStart(2, '0')}m` : `${m}m`
}

export const fmtKm = (m: number | null) => (m ? `${(m / 1000).toFixed(2)} km` : '-')

/** min/km as m:ss from speed in m/s */
export function fmtPace(speedMs: number | null): string {
  if (!speedMs) return '-'
  const secPerKm = 1000 / speedMs
  const m = Math.floor(secPerKm / 60)
  const s = Math.round(secPerKm % 60)
  return `${m}:${String(s).padStart(2, '0')} /km`
}

export const avg = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null)

export type SportGroup = 'Run' | 'Swim' | 'Bike' | 'Strength' | 'Other'
export function sportGroup(sport: string | null): SportGroup {
  const s = sport ?? ''
  if (/running/.test(s)) return 'Run'
  if (/swim/.test(s)) return 'Swim'
  if (/cycling|biking|ride/.test(s)) return 'Bike'
  if (/strength/.test(s)) return 'Strength'
  return 'Other'
}
export const SPORT_COLORS: Record<SportGroup, string> = {
  Run: 'var(--series-1)',
  Swim: 'var(--series-2)',
  Bike: 'var(--series-3)',
  Strength: 'var(--series-4)',
  Other: 'var(--series-5)',
}
export const sportLabel = (sport: string | null) =>
  (sport ?? 'other').replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())
