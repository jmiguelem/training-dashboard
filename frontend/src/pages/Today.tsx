import type { Activity, Cycle, GarminDaily, Recovery, Sleep } from '../api'
import { Loading, Stat } from '../components/ui'
import {
  avg,
  fmtDuration,
  fmtKm,
  hours,
  parseTs,
  sportLabel,
} from '../lib/format'
import { useApi } from '../lib/useApi'

function band(score: number | null) {
  if (score == null) return '-'
  if (score >= 67) return 'High'
  if (score >= 34) return 'Moderate'
  return 'Low'
}

export default function Today({ reloadKey }: { reloadKey: number }) {
  const rec = useApi<Recovery[]>('/api/recovery?days=35', reloadKey)
  const sleep = useApi<Sleep[]>('/api/sleep?days=7', reloadKey)
  const cycles = useApi<Cycle[]>('/api/cycles?days=3', reloadKey)
  const acts = useApi<Activity[]>('/api/activities?days=14', reloadKey)
  const daily = useApi<GarminDaily[]>('/api/garmin/daily?days=3', reloadKey)

  const recs = rec.data ?? []
  const latest = recs[recs.length - 1]
  const baseline = avg(
    recs
      .slice(0, -1)
      .map((r) => r.hrv_rmssd_ms)
      .filter((x): x is number => x != null),
  )
  const hrvDelta =
    latest?.hrv_rmssd_ms != null && baseline ? ((latest.hrv_rmssd_ms - baseline) / baseline) * 100 : null
  const lastSleep = (sleep.data ?? []).filter((s) => !s.nap).slice(-1)[0]
  const sleepMs = lastSleep
    ? (lastSleep.light_ms ?? 0) + (lastSleep.sws_ms ?? 0) + (lastSleep.rem_ms ?? 0)
    : 0
  const cyc = (cycles.data ?? []).slice(-1)[0]
  const lastAct = (acts.data ?? []).slice(-1)[0]
  const bb = (daily.data ?? []).filter((d) => d.body_battery_high != null).slice(-1)[0]

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Today</h1>
      <Loading error={rec.error} loading={rec.loading && !rec.data} />
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat
          label="Recovery"
          value={latest?.recovery_score != null ? `${Math.round(latest.recovery_score)}%` : '-'}
          sub={`${band(latest?.recovery_score ?? null)} · resting HR ${latest?.resting_hr ?? '-'}`}
        />
        <Stat
          label="HRV"
          value={latest?.hrv_rmssd_ms != null ? `${Math.round(latest.hrv_rmssd_ms)} ms` : '-'}
          sub={
            hrvDelta != null
              ? `${hrvDelta >= 0 ? '+' : ''}${hrvDelta.toFixed(0)}% vs 30-day average`
              : undefined
          }
        />
        <Stat
          label="Last sleep"
          value={lastSleep ? `${hours(sleepMs).toFixed(1)} h` : '-'}
          sub={
            lastSleep?.performance_pct != null
              ? `${Math.round(lastSleep.performance_pct)}% performance`
              : undefined
          }
        />
        <Stat
          label="Day strain"
          value={cyc?.strain != null ? cyc.strain.toFixed(1) : '-'}
          sub="Whoop, 0-21"
        />
        <Stat
          label="Body battery"
          value={bb ? `${bb.body_battery_high}` : '-'}
          sub={bb ? `Peak on ${bb.date}, low ${bb.body_battery_low}` : 'Garmin'}
        />
        <Stat
          label="Steps"
          value={bb?.steps != null ? bb.steps.toLocaleString() : '-'}
          sub={bb ? bb.date : undefined}
        />
      </div>
      {lastAct && (
        <section className="card">
          <div className="muted text-xs uppercase tracking-wide">Last activity</div>
          <div className="mt-1 text-lg font-semibold">{lastAct.name ?? sportLabel(lastAct.sport)}</div>
          <div className="secondary text-sm">
            {parseTs(lastAct.start).toLocaleDateString(undefined, {
              weekday: 'long',
              month: 'short',
              day: 'numeric',
            })}
            {' · '}
            {sportLabel(lastAct.sport)}
            {' · '}
            {fmtDuration(lastAct.duration_s)}
            {lastAct.distance_m ? ` · ${fmtKm(lastAct.distance_m)}` : ''}
            {lastAct.avg_hr ? ` · avg HR ${Math.round(lastAct.avg_hr)}` : ''}
          </div>
        </section>
      )}
    </div>
  )
}
