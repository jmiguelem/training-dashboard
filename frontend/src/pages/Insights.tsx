import { Loading, Stat } from '../components/ui'
import { useApi } from '../lib/useApi'

type Flag = { level: 'warn' | 'info' | 'good'; title: string; detail: string }
type Metrics = Record<string, number | null>
type Insights = { metrics: Metrics; flags: Flag[] }

const LEVEL: Record<Flag['level'], { icon: string; label: string; color: string }> = {
  warn: { icon: '▲', label: 'Watch', color: 'var(--series-2)' },
  info: { icon: '●', label: 'Note', color: 'var(--text-muted)' },
  good: { icon: '✓', label: 'Good', color: 'var(--series-3)' },
}

const n = (v: number | null | undefined, suffix = '') => (v == null ? '-' : `${v}${suffix}`)
const signed = (v: number | null | undefined) =>
  v == null ? '-' : `${v > 0 ? '+' : ''}${v}%`

export default function InsightsPage({ reloadKey }: { reloadKey: number }) {
  const { data, error, loading } = useApi<Insights>('/api/insights', reloadKey)
  const m = data?.metrics

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Insights</h1>
      <Loading error={error} loading={loading && !data} />
      {data && (
        <>
          <section className="card">
            <h2 className="text-base font-semibold">What stands out</h2>
            {data.flags.length === 0 ? (
              <p className="secondary mt-2 text-sm">Nothing unusual. Keep going.</p>
            ) : (
              <ul className="mt-3 space-y-3">
                {data.flags.map((f) => {
                  const l = LEVEL[f.level]
                  return (
                    <li key={f.title} className="flex gap-3">
                      <span
                        aria-hidden
                        className="mt-0.5 w-5 text-center text-sm"
                        style={{ color: l.color }}
                      >
                        {l.icon}
                      </span>
                      <div>
                        <div className="text-sm font-medium">
                          {f.title} <span className="muted font-normal">({l.label})</span>
                        </div>
                        <div className="secondary text-sm">{f.detail}</div>
                      </div>
                    </li>
                  )
                })}
              </ul>
            )}
          </section>
          {m && (
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
              <Stat
                label="Training this week"
                value={`${n(m.training_minutes_7d)} min`}
                sub={`${signed(m.load_change_pct)} vs prior week`}
              />
              <Stat
                label="Load ratio"
                value={n(m.acute_chronic_ratio)}
                sub="This week vs 4-week average"
              />
              <Stat
                label="HRV (7d)"
                value={`${n(m.hrv_7d)} ms`}
                sub={`${signed(m.hrv_change_pct)} vs 30-day`}
              />
              <Stat
                label="Resting HR (7d)"
                value={`${n(m.resting_hr_7d)} bpm`}
                sub={`30-day ${n(m.resting_hr_30d)}`}
              />
              <Stat
                label="Sleep (7d avg)"
                value={`${n(m.sleep_hours_7d)} h`}
                sub={`Debt ${n(m.sleep_debt_hours_7d)} h vs 8 h/night`}
              />
              <Stat
                label="Sessions"
                value={`${n(m.sessions_7d)} / wk`}
                sub={`${n(m.sessions_28d)} in 4 weeks`}
              />
              <Stat
                label="Run distance (4w)"
                value={`${n(m.run_km_4w)} km`}
                sub={`Prior 4w ${n(m.run_km_prev_4w)} km`}
              />
              <Stat
                label="Run efficiency"
                value={signed(m.run_efficiency_change_pct)}
                sub="Last 4 runs vs 4 before"
              />
            </div>
          )}
          <p className="muted text-xs">General fitness guidance, not medical advice.</p>
        </>
      )}
    </div>
  )
}
