import type { ReactNode } from 'react'

export function Stat({
  label,
  value,
  sub,
}: {
  label: string
  value: ReactNode
  sub?: ReactNode
}) {
  return (
    <div className="card">
      <div className="muted text-xs uppercase tracking-wide">{label}</div>
      <div className="mt-1 text-3xl font-semibold tabular-nums">{value}</div>
      {sub && <div className="secondary mt-1 text-sm">{sub}</div>}
    </div>
  )
}

export function ChartCard({
  title,
  subtitle,
  legend,
  children,
}: {
  title: string
  subtitle?: string
  legend?: { label: string; color: string }[]
  children: ReactNode
}) {
  return (
    <section className="card">
      <h2 className="text-base font-semibold">{title}</h2>
      {subtitle && <p className="secondary text-sm">{subtitle}</p>}
      {legend && legend.length > 1 && (
        <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm">
          {legend.map((l) => (
            <li key={l.label} className="flex items-center gap-1.5">
              <span
                aria-hidden
                className="inline-block h-2.5 w-2.5 rounded-sm"
                style={{ background: l.color }}
              />
              <span className="secondary">{l.label}</span>
            </li>
          ))}
        </ul>
      )}
      <div className="mt-3 h-64">{children}</div>
    </section>
  )
}

export const tooltipStyle = {
  contentStyle: {
    background: 'var(--surface-1)',
    border: '1px solid var(--border)',
    borderRadius: 8,
    color: 'var(--text-primary)',
  },
  labelStyle: { color: 'var(--text-secondary)' },
  itemStyle: { color: 'var(--text-primary)' },
  cursor: { stroke: 'var(--border)', fill: 'var(--grid)', fillOpacity: 0.4 },
}

export function Loading({ error, loading }: { error: string | null; loading: boolean }) {
  if (error) return <p className="text-sm">Could not load data: {error}</p>
  if (loading) return <p className="muted text-sm">Loading…</p>
  return null
}

export function RangePicker({
  value,
  onChange,
  options = [30, 90, 180, 365],
}: {
  value: number
  onChange: (n: number) => void
  options?: number[]
}) {
  return (
    <div role="group" aria-label="Date range" className="flex gap-1">
      {options.map((o) => (
        <button
          key={o}
          onClick={() => onChange(o)}
          aria-pressed={value === o}
          className="rounded-md border px-3 py-1 text-sm"
          style={{
            borderColor: 'var(--border)',
            background: value === o ? 'var(--text-primary)' : 'var(--surface-1)',
            color: value === o ? 'var(--surface-1)' : 'var(--text-secondary)',
          }}
        >
          {o}d
        </button>
      ))}
    </div>
  )
}
