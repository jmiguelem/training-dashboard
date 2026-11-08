import { useCallback, useEffect, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { ChartCard, Loading, tooltipStyle } from '../components/ui'
import { shortDate } from '../lib/format'

type LiftSet = {
  id: number
  exercise: string
  name: string
  reps: number | null
  weight_kg: number | null
  duration_s: number | null
  rest_s: number | null
  edited: number
  suspect: boolean
  e1rm: number | null
}
type Session = {
  activity_id: number
  date: string
  name: string | null
  minutes: number
  sets: LiftSet[]
  volume_kg: number
  suspect_sets: number
}
type Hist = { date: string; top_weight_kg: number | null; top_reps: number | null; best_e1rm: number | null; sets: number }
type Exercise = {
  exercise: string
  name: string
  sessions: number
  best_weight_kg: number | null
  best_e1rm: number | null
  history: Hist[]
}
type Data = {
  sessions: Session[]
  exercises: Exercise[]
  weekly: { week: string; sessions: number; sets: number; volume_kg: number }[]
}

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const r = await fetch(path, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(data.detail ?? `Request failed (${r.status})`)
  return data as T
}

const input = {
  borderColor: 'var(--border)',
  background: 'var(--surface-0)',
  color: 'var(--text-primary)',
}

function SetRow({ s, onChange }: { s: LiftSet; onChange: () => void }) {
  const [ex, setEx] = useState(s.name)
  const [reps, setReps] = useState(String(s.reps ?? ''))
  const [kg, setKg] = useState(String(s.weight_kg ?? ''))
  const [err, setErr] = useState<string | null>(null)

  async function save(fields: Record<string, unknown>) {
    setErr(null)
    try {
      await req('PATCH', `/api/lifts/sets/${s.id}`, fields)
      onChange()
    } catch (e) {
      setErr((e as Error).message)
    }
  }
  const dirtyEx = ex.trim().toLowerCase() !== s.name.toLowerCase()
  return (
    <tr style={{ borderTop: '1px solid var(--border)' }}>
      <td className="py-1 pr-2">
        <input
          aria-label="Exercise"
          value={ex}
          onChange={(e) => setEx(e.target.value)}
          onBlur={() => dirtyEx && ex.trim() && save({ exercise: ex })}
          className="w-full min-w-[9rem] rounded border px-2 py-1 text-sm"
          style={input}
        />
      </td>
      <td className="py-1 pr-2">
        <input
          aria-label="Reps"
          type="number"
          min={0}
          value={reps}
          onChange={(e) => setReps(e.target.value)}
          onBlur={() => reps !== String(s.reps ?? '') && reps !== '' && save({ reps: Number(reps) })}
          className="w-16 rounded border px-2 py-1 text-sm tabular-nums"
          style={input}
        />
      </td>
      <td className="py-1 pr-2">
        <input
          aria-label="Weight in kilograms"
          type="number"
          min={0}
          step={0.5}
          value={kg}
          onChange={(e) => setKg(e.target.value)}
          onBlur={() => kg !== String(s.weight_kg ?? '') && kg !== '' && save({ weight_kg: Number(kg) })}
          className="w-20 rounded border px-2 py-1 text-sm tabular-nums"
          style={input}
        />
      </td>
      <td className="secondary whitespace-nowrap py-1 pr-2 text-xs tabular-nums">
        {s.duration_s != null ? `${Math.round(s.duration_s)}s` : '-'}
        {s.rest_s != null ? ` / rest ${Math.round(s.rest_s)}s` : ''}
      </td>
      <td className="whitespace-nowrap py-1 pr-2 text-xs">
        {s.suspect && <span title="Very short or zero reps: probably a missed set start">⚠ Check</span>}
        {s.edited ? <span className="muted">Edited</span> : null}
        {err && <span> {err}</span>}
      </td>
      <td className="py-1">
        <button
          onClick={() => save({ deleted: true })}
          aria-label="Delete set"
          className="muted px-1 text-sm"
        >
          ✕
        </button>
      </td>
    </tr>
  )
}

function SessionCard({ s, open, onChange }: { s: Session; open: boolean; onChange: () => void }) {
  const [adding, setAdding] = useState(false)
  const [ex, setEx] = useState(s.sets[s.sets.length - 1]?.name ?? '')
  const [reps, setReps] = useState('')
  const [kg, setKg] = useState('')
  const [err, setErr] = useState<string | null>(null)

  async function add() {
    setErr(null)
    try {
      await req('POST', '/api/lifts/sets', {
        activity_id: s.activity_id,
        exercise: ex,
        reps: Number(reps),
        weight_kg: Number(kg || 0),
      })
      setReps('')
      onChange()
    } catch (e) {
      setErr((e as Error).message)
    }
  }
  return (
    <details className="card" open={open}>
      <summary className="cursor-pointer text-sm">
        <span className="font-semibold">{shortDate(s.date + 'T12:00:00')}</span>
        <span className="secondary">
          {' · '}
          {s.minutes} min · {s.sets.length} sets · {s.volume_kg.toLocaleString()} kg volume
        </span>
        {s.suspect_sets > 0 && <span> · ⚠ {s.suspect_sets} to check</span>}
      </summary>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full text-left">
          <thead className="muted text-xs uppercase">
            <tr>
              <th className="pr-2 font-medium">Exercise</th>
              <th className="pr-2 font-medium">Reps</th>
              <th className="pr-2 font-medium">kg</th>
              <th className="pr-2 font-medium">Set time</th>
              <th />
              <th />
            </tr>
          </thead>
          <tbody>
            {s.sets.map((x) => (
              <SetRow key={`${x.id}-${x.reps}-${x.weight_kg}-${x.exercise}`} s={x} onChange={onChange} />
            ))}
          </tbody>
        </table>
        {adding ? (
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <input
              aria-label="Exercise name"
              value={ex}
              onChange={(e) => setEx(e.target.value)}
              placeholder="Exercise"
              className="rounded border px-2 py-1 text-sm"
              style={input}
            />
            <input
              aria-label="Reps"
              type="number"
              value={reps}
              onChange={(e) => setReps(e.target.value)}
              placeholder="Reps"
              className="w-16 rounded border px-2 py-1 text-sm"
              style={input}
            />
            <input
              aria-label="Weight in kilograms"
              type="number"
              step={0.5}
              value={kg}
              onChange={(e) => setKg(e.target.value)}
              placeholder="kg"
              className="w-20 rounded border px-2 py-1 text-sm"
              style={input}
            />
            <button
              onClick={add}
              disabled={!ex.trim() || !reps}
              className="rounded-md border px-3 py-1 text-sm disabled:opacity-50"
              style={{ borderColor: 'var(--border)', background: 'var(--surface-1)' }}
            >
              Add set
            </button>
            <button onClick={() => setAdding(false)} className="muted text-sm underline">
              Cancel
            </button>
            {err && <span className="text-sm">{err}</span>}
          </div>
        ) : (
          <button onClick={() => setAdding(true)} className="secondary mt-2 text-sm underline">
            + Add a set
          </button>
        )}
      </div>
    </details>
  )
}

export default function Lifts({ reloadKey }: { reloadKey: number }) {
  const [data, setData] = useState<Data | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pick, setPick] = useState<string | null>(null)

  const load = useCallback(() => {
    req<Data>('GET', '/api/lifts?days=180')
      .then((d) => {
        setData(d)
        setError(null)
      })
      .catch((e: Error) => setError(e.message))
  }, [])
  useEffect(load, [load, reloadKey])

  const ex = data?.exercises.find((e) => e.exercise === (pick ?? data.exercises[0]?.exercise))
  const rows = (ex?.history ?? []).map((h) => ({
    date: shortDate(h.date + 'T12:00:00'),
    'Top weight (kg)': h.top_weight_kg,
    'Estimated 1RM (kg)': h.best_e1rm,
  }))
  const weekly = (data?.weekly ?? []).map((w) => ({
    week: shortDate(w.week + 'T12:00:00'),
    'Volume (kg)': w.volume_kg,
  }))

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Lifts</h1>
      <Loading error={error} loading={!data && !error} />
      {data && (
        <>
          <div className="grid gap-4 lg:grid-cols-2">
            <ChartCard title="Weekly volume" subtitle="Sets × reps × kg, excluding sets to check">
              <ResponsiveContainer>
                <BarChart data={weekly}>
                  <CartesianGrid vertical={false} />
                  <XAxis dataKey="week" minTickGap={24} tickLine={false} />
                  <YAxis width={48} tickLine={false} axisLine={false} />
                  <Tooltip {...tooltipStyle} />
                  <Bar dataKey="Volume (kg)" fill="var(--series-4)" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>
            <section className="card">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-base font-semibold">Exercise progress</h2>
                <select
                  aria-label="Exercise"
                  value={ex?.exercise ?? ''}
                  onChange={(e) => setPick(e.target.value)}
                  className="rounded border px-2 py-1 text-sm"
                  style={input}
                >
                  {data.exercises.map((e) => (
                    <option key={e.exercise} value={e.exercise}>
                      {e.name} ({e.sessions})
                    </option>
                  ))}
                </select>
              </div>
              {ex && (
                <p className="secondary mt-1 text-sm">
                  Best {ex.best_weight_kg ?? '-'} kg · est. 1RM {ex.best_e1rm ?? '-'} kg ·{' '}
                  {ex.sessions} sessions
                </p>
              )}
              <div className="mt-3 h-52">
                {rows.length < 2 ? (
                  <p className="muted text-sm">Needs at least two sessions of this exercise.</p>
                ) : (
                  <ResponsiveContainer>
                    <LineChart data={rows}>
                      <CartesianGrid vertical={false} />
                      <XAxis dataKey="date" minTickGap={24} tickLine={false} />
                      <YAxis width={40} tickLine={false} axisLine={false} domain={['auto', 'auto']} />
                      <Tooltip {...tooltipStyle} />
                      <Legend iconType="square" />
                      <Line
                        dataKey="Top weight (kg)"
                        stroke="var(--series-1)"
                        strokeWidth={2}
                        dot={{ r: 4, stroke: 'var(--surface-1)', strokeWidth: 2 }}
                        connectNulls
                      />
                      <Line
                        dataKey="Estimated 1RM (kg)"
                        stroke="var(--series-2)"
                        strokeWidth={2}
                        dot={{ r: 4, stroke: 'var(--surface-1)', strokeWidth: 2 }}
                        connectNulls
                      />
                    </LineChart>
                  </ResponsiveContainer>
                )}
              </div>
              <p className="muted mt-2 text-xs">
                Estimated 1RM uses the Epley formula and is only shown for sets of 12 reps or fewer.
              </p>
            </section>
          </div>
          <div>
            <h2 className="mb-2 text-base font-semibold">Sessions</h2>
            <p className="muted mb-3 text-sm">
              Fix any set here. Edits are kept when Garmin syncs again. Sets marked ⚠ Check are very
              short or have no reps (often a missed set start) and are left out of the stats until you
              fix them.
            </p>
            <div className="space-y-3">
              {data.sessions.map((s, i) => (
                <SessionCard key={s.activity_id} s={s} open={i === 0} onChange={load} />
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
