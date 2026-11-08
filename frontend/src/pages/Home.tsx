import { useCallback, useEffect, useState } from 'react'
import type { Activity, Cycle, GarminDaily, Recovery, Sleep } from '../api'
import { Loading, Stat } from '../components/ui'
import { avg, fmtDuration, fmtKm, hours, parseTs, SPORT_COLORS, sportLabel, type SportGroup } from '../lib/format'
import { useApi } from '../lib/useApi'

type Matched = { type: string; minutes: number; km: number }
type Session = {
  item: string
  sport: 'run' | 'swim' | 'bike' | 'gym' | 'other'
  title: string
  details: string
  duration_min: number
  intensity: 'easy' | 'moderate' | 'hard'
  condition: string
  checked: boolean
  done: boolean
  matched: Matched[]
}
type Day = { day: string; date: string; is_today: boolean; is_past: boolean; sessions: Session[] }
type Rec = { item: string; category: string; text: string; condition: string; checked: boolean }
type Plan = {
  week_key: string
  week_start?: string
  days: Day[] | null
  focus?: string
  created_at?: string
  recommendations?: Rec[]
  progress?: { done: number; total: number; recs_done: number; recs_total: number }
}

const SPORT_GROUP: Record<Session['sport'], SportGroup> = {
  run: 'Run',
  swim: 'Swim',
  bike: 'Bike',
  gym: 'Strength',
  other: 'Other',
}
const INTENSITY: Record<Session['intensity'], { label: string; mark: string }> = {
  easy: { label: 'Easy', mark: '○' },
  moderate: { label: 'Moderate', mark: '◐' },
  hard: { label: 'Hard', mark: '●' },
}
const CATEGORY: Record<string, string> = {
  sleep: 'Sleep',
  recovery: 'Recovery',
  training: 'Training',
  load: 'Load',
  nutrition: 'Nutrition',
  other: 'Note',
}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const r = await fetch(path, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(data.detail ?? `Request failed (${r.status})`)
  return data as T
}

function band(score: number | null) {
  if (score == null) return '-'
  if (score >= 67) return 'High'
  if (score >= 34) return 'Moderate'
  return 'Low'
}

function Check({
  checked,
  disabled,
  label,
  onChange,
}: {
  checked: boolean
  disabled?: boolean
  label: string
  onChange: (v: boolean) => void
}) {
  return (
    <input
      type="checkbox"
      aria-label={label}
      checked={checked}
      disabled={disabled}
      onChange={(e) => onChange(e.target.checked)}
      className="h-5 w-5 shrink-0 cursor-pointer accent-[var(--series-1)] disabled:cursor-default"
    />
  )
}

function SessionItem({
  x,
  past,
  onCheck,
}: {
  x: Session
  past: boolean
  onCheck: (item: string, v: boolean) => void
}) {
  const color = SPORT_COLORS[SPORT_GROUP[x.sport]]
  return (
    <div className="flex gap-3">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span
            className="inline-flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide"
            style={{ color: 'var(--text-secondary)' }}
          >
            <span aria-hidden className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: color }} />
            {x.sport}
          </span>
          <span className="text-sm font-semibold">{x.title}</span>
          <span className="secondary text-xs tabular-nums">
            {x.duration_min} min · {INTENSITY[x.intensity].mark} {INTENSITY[x.intensity].label}
          </span>
        </div>
        {x.details && <p className="secondary mt-1 text-sm">{x.details}</p>}
        {x.condition && (
          <p className="mt-1 text-sm">
            <span aria-hidden>⚑ </span>
            <span className="font-medium">If: </span>
            <span className="secondary">{x.condition}</span>
          </p>
        )}
        {x.matched.length > 0 && (
          <p className="mt-1 text-xs" style={{ color: 'var(--series-3)' }}>
            ✓ Garmin logged {x.matched.map((m) => `${m.minutes} min${m.km ? `, ${m.km} km` : ''}`).join(' + ')}
          </p>
        )}
        {past && !x.done && <p className="muted mt-1 text-xs">Not logged</p>}
      </div>
      <Check
        checked={x.done}
        disabled={x.matched.length > 0}
        label={`Mark done: ${x.title}`}
        onChange={(v) => onCheck(x.item, v)}
      />
    </div>
  )
}

function DayRow({ d, onCheck }: { d: Day; onCheck: (item: string, v: boolean) => void }) {
  const date = new Date(d.date + 'T12:00:00')
  const allDone = d.sessions.length > 0 && d.sessions.every((x) => x.done)
  return (
    <li
      className="flex gap-3 rounded-lg px-3 py-3"
      style={{
        border: `1px solid ${d.is_today ? 'var(--text-secondary)' : 'var(--border)'}`,
        background: allDone ? 'var(--surface-0)' : 'transparent',
        opacity: d.sessions.length === 0 ? 0.7 : 1,
      }}
      aria-current={d.is_today ? 'date' : undefined}
    >
      <div className="w-12 shrink-0 text-center">
        <div className="text-sm font-semibold">{d.day}</div>
        <div className="muted text-xs tabular-nums">{date.getDate()}</div>
        {d.is_today && <div className="mt-0.5 text-[10px] font-semibold uppercase">Today</div>}
      </div>
      <div className="min-w-0 flex-1 space-y-3">
        {d.sessions.length === 0 ? (
          <p className="muted text-sm">{d.is_past ? '–' : 'Rest day'}</p>
        ) : (
          d.sessions.map((x) => <SessionItem key={x.item} x={x} past={d.is_past} onCheck={onCheck} />)
        )}
      </div>
    </li>
  )
}

function PlanCard({ reloadKey }: { reloadKey: number }) {
  const [plan, setPlan] = useState<Plan | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    void call<Plan>('GET', '/api/plan')
      .then(setPlan)
      .catch((e: Error) => setError(e.message))
  }, [])
  useEffect(load, [load, reloadKey])

  async function generate() {
    setBusy(true)
    setError(null)
    try {
      setPlan(await call<Plan>('POST', '/api/plan/generate'))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }
  async function check(item: string, done: boolean) {
    try {
      setPlan(await call<Plan>('PUT', '/api/plan/check', { item, done }))
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const has = !!plan?.days
  const pr = plan?.progress
  const pct = pr && pr.total ? Math.round((pr.done / pr.total) * 100) : 0

  return (
    <>
      <section className="card">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h2 className="text-base font-semibold">
              {plan?.week_start && new Date(plan.week_start + 'T12:00:00') > new Date()
                ? `Next week's plan (from ${new Date(plan.week_start + 'T12:00:00').toLocaleDateString(undefined, { month: 'short', day: 'numeric' })})`
                : "This week's plan"}
            </h2>
            {plan?.focus && <p className="secondary mt-1 text-sm">{plan.focus}</p>}
          </div>
          <button
            onClick={generate}
            disabled={busy}
            className="rounded-md border px-3 py-1.5 text-sm disabled:opacity-50"
            style={{ borderColor: 'var(--border)', background: 'var(--surface-1)' }}
          >
            {busy ? 'Planning…' : has ? 'Regenerate' : 'Generate plan'}
          </button>
        </div>
        {error && <p className="mt-2 text-sm">{error}</p>}
        {has && pr && (
          <div className="mt-3">
            <div className="flex justify-between text-sm">
              <span>
                {pr.done} of {pr.total} sessions done
              </span>
              <span className="muted tabular-nums">{pct}%</span>
            </div>
            <div
              role="progressbar"
              aria-label="Week progress"
              aria-valuenow={pct}
              aria-valuemin={0}
              aria-valuemax={100}
              className="mt-1 h-2 overflow-hidden rounded-full"
              style={{ background: 'var(--grid)' }}
            >
              <div className="h-full rounded-full" style={{ width: `${pct}%`, background: 'var(--series-3)' }} />
            </div>
          </div>
        )}
        {has ? (
          <ul className="mt-4 space-y-2">
            {plan!.days!.map((d) => (
              <DayRow key={d.date} d={d} onCheck={check} />
            ))}
          </ul>
        ) : (
          !error && (
            <p className="muted mt-3 text-sm">
              No plan for this week yet. It is written automatically on Sunday night, or you can
              generate it now. It uses your goal, recovery, sleep and training data.
            </p>
          )
        )}
        {has && plan?.created_at && (
          <p className="muted mt-3 text-xs">
            Written by your coach{' '}
            {new Date(plan.created_at).toLocaleString(undefined, { weekday: 'short', hour: 'numeric', minute: '2-digit' })}
            . General fitness guidance, not medical advice.
          </p>
        )}
      </section>

      {has && plan?.recommendations && plan.recommendations.length > 0 && (
        <section className="card">
          <div className="flex items-baseline justify-between">
            <h2 className="text-base font-semibold">Coach recommendations</h2>
            {pr && (
              <span className="muted text-sm tabular-nums">
                {pr.recs_done} of {pr.recs_total} done
              </span>
            )}
          </div>
          <ul className="mt-3 space-y-3">
            {plan.recommendations.map((r) => (
              <li key={r.item} className="flex gap-3">
                <Check checked={r.checked} label={`Mark done: ${r.text}`} onChange={(v) => check(r.item, v)} />
                <div className="min-w-0">
                  <div className="text-sm">
                    <span className="muted mr-2 text-xs font-medium uppercase tracking-wide">
                      {CATEGORY[r.category] ?? 'Note'}
                    </span>
                    <span style={{ textDecoration: r.checked ? 'line-through' : 'none' }}>{r.text}</span>
                  </div>
                  {r.condition && (
                    <div className="secondary text-sm">
                      <span aria-hidden>⚑ </span>
                      {r.condition}
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  )
}

export default function Home({ reloadKey }: { reloadKey: number }) {
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
  const sleepMs = lastSleep ? (lastSleep.light_ms ?? 0) + (lastSleep.sws_ms ?? 0) + (lastSleep.rem_ms ?? 0) : 0
  const cyc = (cycles.data ?? []).slice(-1)[0]
  const lastAct = (acts.data ?? []).slice(-1)[0]
  const bb = (daily.data ?? []).filter((d) => d.body_battery_high != null).slice(-1)[0]

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="text-xl font-semibold">Home</h1>
        <span className="muted text-sm">
          {new Date().toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })}
        </span>
      </div>
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
          sub={hrvDelta != null ? `${hrvDelta >= 0 ? '+' : ''}${hrvDelta.toFixed(0)}% vs 30-day average` : undefined}
        />
        <Stat
          label="Last sleep"
          value={lastSleep ? `${hours(sleepMs).toFixed(1)} h` : '-'}
          sub={lastSleep?.performance_pct != null ? `${Math.round(lastSleep.performance_pct)}% performance` : undefined}
        />
        <Stat label="Day strain" value={cyc?.strain != null ? cyc.strain.toFixed(1) : '-'} sub="Whoop, 0-21" />
      </div>
      <PlanCard reloadKey={reloadKey} />
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat
          label="Body battery"
          value={bb ? `${bb.body_battery_high}` : '-'}
          sub={bb ? `Peak on ${bb.date}, low ${bb.body_battery_low}` : 'Garmin'}
        />
        <Stat label="Steps" value={bb?.steps != null ? bb.steps.toLocaleString() : '-'} sub={bb ? bb.date : undefined} />
        {lastAct && (
          <section className="card col-span-2">
            <div className="muted text-xs uppercase tracking-wide">Last activity</div>
            <div className="mt-1 text-lg font-semibold">{lastAct.name ?? sportLabel(lastAct.sport)}</div>
            <div className="secondary text-sm">
              {parseTs(lastAct.start).toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' })}
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
    </div>
  )
}
