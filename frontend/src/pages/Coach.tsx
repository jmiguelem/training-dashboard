import { useCallback, useEffect, useRef, useState } from 'react'

type Summary = { text: string | null; created_at?: string }
type Msg = { role: 'user' | 'assistant'; content: string }
type Note = { week_key: string; text: string }
type Goal = {
  goal: string
  race_name: string
  race_date: string
  weeks_to_race: number | null
  items: { sport: string; longest_km: number; target_km: number; percent: number }[]
  run_km_last_4_weeks: number
  note: string
}
type Profile = {
  goal: string
  race_name: string
  race_date: string
  max_hr: number
  gym_days_per_week: number
  gym_split: string
  background: string
  injuries: string
  notes: string
}

async function send<T>(method: string, path: string, body?: unknown): Promise<T> {
  const r = await fetch(path, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(data.detail ?? `Request failed (${r.status})`)
  return data as T
}
const getJson = <T,>(path: string) => send<T>('GET', path)

const SPLIT_PRESETS = ['Upper/Lower', 'Push/Pull/Legs', 'Full body', 'Bro split']
const SUGGESTIONS = [
  'Should I run today?',
  'Am I on track for my goal?',
  'Am I sleeping enough to recover from my gym days?',
]
const field = {
  borderColor: 'var(--border)',
  background: 'var(--surface-0)',
  color: 'var(--text-primary)',
}
const btn = { borderColor: 'var(--border)', background: 'var(--surface-1)' }

function GoalCard({ goal }: { goal: Goal }) {
  return (
    <section className="card">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-base font-semibold">Goal: {goal.race_name}</h2>
        <span className="secondary text-sm tabular-nums">
          {goal.weeks_to_race != null ? `${goal.weeks_to_race} weeks to go` : 'No race date set'}
          {goal.race_date ? ` · ${goal.race_date}` : ''}
        </span>
      </div>
      <p className="secondary mt-1 text-sm">{goal.goal}</p>
      <div className="mt-3 space-y-2">
        {goal.items.map((i) => (
          <div key={i.sport}>
            <div className="flex justify-between text-sm">
              <span>{i.sport}</span>
              <span className="secondary tabular-nums">
                longest {i.longest_km} km of {i.target_km} km
              </span>
            </div>
            <div
              role="progressbar"
              aria-label={`${i.sport} readiness`}
              aria-valuenow={i.percent}
              aria-valuemin={0}
              aria-valuemax={100}
              className="mt-1 h-2 overflow-hidden rounded-full"
              style={{ background: 'var(--grid)' }}
            >
              <div
                className="h-full rounded-full"
                style={{ width: `${i.percent}%`, background: 'var(--series-1)' }}
              />
            </div>
          </div>
        ))}
      </div>
      <p className="muted mt-3 text-xs">
        Run volume last 4 weeks: {goal.run_km_last_4_weeks} km. {goal.note}
      </p>
    </section>
  )
}

function ProfileForm({ onSaved }: { onSaved: () => void }) {
  const [p, setP] = useState<Profile | null>(null)
  const [msg, setMsg] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    void getJson<Profile>('/api/profile').then(setP)
  }, [])
  if (!p) return null
  const set = <K extends keyof Profile>(k: K, v: Profile[K]) => setP({ ...p, [k]: v })

  async function save() {
    setBusy(true)
    setMsg(null)
    try {
      setP(await send<Profile>('PUT', '/api/profile', p))
      setMsg('Saved')
      onSaved()
    } catch (e) {
      setMsg((e as Error).message)
    } finally {
      setBusy(false)
    }
  }
  const text = (k: 'goal' | 'race_name' | 'background' | 'injuries' | 'notes', label: string, rows = 2) => (
    <label className="block text-sm">
      <span className="secondary">{label}</span>
      <textarea
        value={p[k]}
        rows={rows}
        onChange={(e) => set(k, e.target.value)}
        className="mt-1 w-full rounded-md border px-3 py-2 text-sm"
        style={field}
      />
    </label>
  )
  return (
    <details className="card">
      <summary className="cursor-pointer text-base font-semibold">Profile and goals</summary>
      <div className="mt-3 space-y-3">
        {text('goal', 'Goal')}
        <div className="grid gap-3 sm:grid-cols-4">
          <label className="block text-sm sm:col-span-2">
            <span className="secondary">Race name</span>
            <input
              value={p.race_name}
              onChange={(e) => set('race_name', e.target.value)}
              className="mt-1 w-full rounded-md border px-3 py-2 text-sm"
              style={field}
            />
          </label>
          <label className="block text-sm">
            <span className="secondary">Race date</span>
            <input
              type="date"
              value={p.race_date}
              onChange={(e) => set('race_date', e.target.value)}
              className="mt-1 w-full rounded-md border px-3 py-2 text-sm"
              style={field}
            />
          </label>
          <div className="grid grid-cols-2 gap-3">
            <label className="block text-sm">
              <span className="secondary">Max HR</span>
              <input
                type="number"
                value={p.max_hr}
                onChange={(e) => set('max_hr', Number(e.target.value))}
                className="mt-1 w-full rounded-md border px-3 py-2 text-sm"
                style={field}
              />
            </label>
            <label className="block text-sm">
              <span className="secondary">Gym days</span>
              <input
                type="number"
                min={0}
                max={7}
                value={p.gym_days_per_week}
                onChange={(e) => set('gym_days_per_week', Number(e.target.value))}
                className="mt-1 w-full rounded-md border px-3 py-2 text-sm"
                style={field}
              />
            </label>
          </div>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block text-sm">
            <span className="secondary">Gym split</span>
            <select
              value={SPLIT_PRESETS.includes(p.gym_split) ? p.gym_split : p.gym_split === '' ? '' : 'custom'}
              onChange={(e) => set('gym_split', e.target.value === 'custom' ? ' ' : e.target.value)}
              className="mt-1 w-full rounded-md border px-3 py-2 text-sm"
              style={field}
            >
              <option value="">Not set</option>
              {SPLIT_PRESETS.map((x) => (
                <option key={x} value={x}>
                  {x}
                </option>
              ))}
              <option value="custom">Custom…</option>
            </select>
          </label>
          {p.gym_split !== '' && !SPLIT_PRESETS.includes(p.gym_split) && (
            <label className="block text-sm">
              <span className="secondary">Describe your split</span>
              <input
                value={p.gym_split.trim() === '' ? '' : p.gym_split}
                onChange={(e) => set('gym_split', e.target.value || ' ')}
                placeholder="e.g. Upper/Lower plus a weekly arms day"
                className="mt-1 w-full rounded-md border px-3 py-2 text-sm"
                style={field}
              />
            </label>
          )}
        </div>
        {text('background', 'Background')}
        {text('injuries', 'Injuries or limits')}
        {text('notes', 'Preferences and notes (days you can train, equipment, pool access…)')}
        <div className="flex items-center gap-3">
          <button
            onClick={save}
            disabled={busy}
            className="rounded-md border px-4 py-2 text-sm disabled:opacity-50"
            style={btn}
          >
            {busy ? 'Saving…' : 'Save profile'}
          </button>
          {msg && <span className="secondary text-sm">{msg}</span>}
        </div>
      </div>
    </details>
  )
}

export default function Coach({ reloadKey }: { reloadKey: number }) {
  const [goal, setGoal] = useState<Goal | null>(null)
  const [summary, setSummary] = useState<Summary | null>(null)
  const [notes, setNotes] = useState<Note[]>([])
  const [summaryBusy, setSummaryBusy] = useState(false)
  const [summaryError, setSummaryError] = useState<string | null>(null)
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [input, setInput] = useState('')
  const [chatBusy, setChatBusy] = useState(false)
  const [chatError, setChatError] = useState<string | null>(null)
  const endRef = useRef<HTMLDivElement>(null)

  const loadAll = useCallback(() => {
    void getJson<Goal>('/api/coach/goal').then(setGoal).catch(() => setGoal(null))
    void getJson<Summary>('/api/coach/summary').then(setSummary).catch(() => setSummary(null))
    void getJson<Note[]>('/api/coach/notes').then(setNotes).catch(() => setNotes([]))
  }, [])
  useEffect(() => {
    loadAll()
    void getJson<{ messages: Msg[] }>('/api/coach/chat')
      .then((d) => setMsgs(d.messages))
      .catch(() => setMsgs([]))
  }, [reloadKey, loadAll])
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'nearest' })
  }, [msgs, chatBusy])

  async function generate(force: boolean) {
    setSummaryBusy(true)
    setSummaryError(null)
    try {
      setSummary(await send<Summary>('POST', `/api/coach/summary?force=${force}`, {}))
      setNotes(await getJson<Note[]>('/api/coach/notes'))
    } catch (e) {
      setSummaryError((e as Error).message)
    } finally {
      setSummaryBusy(false)
    }
  }

  async function ask(text: string) {
    const t = text.trim()
    if (!t || chatBusy) return
    setMsgs((m) => [...m, { role: 'user', content: t }])
    setInput('')
    setChatBusy(true)
    setChatError(null)
    try {
      const { reply } = await send<{ reply: string }>('POST', '/api/coach/chat', { message: t })
      setMsgs((m) => [...m, { role: 'assistant', content: reply }])
    } catch (e) {
      setMsgs((m) => m.slice(0, -1))
      setInput(t)
      setChatError((e as Error).message)
    } finally {
      setChatBusy(false)
    }
  }

  async function clearChat() {
    await send('DELETE', '/api/coach/chat')
    setMsgs([])
  }

  const thisWeekNote = notes[notes.length - 1]

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Coach</h1>
      {goal && <GoalCard goal={goal} />}

      <section className="card">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-base font-semibold">Weekly review</h2>
          <div className="flex items-center gap-3 text-sm">
            {summary?.created_at && (
              <span className="muted">
                {new Date(summary.created_at).toLocaleString(undefined, {
                  month: 'short',
                  day: 'numeric',
                  hour: 'numeric',
                  minute: '2-digit',
                })}
              </span>
            )}
            <button
              onClick={() => generate(!!summary?.text)}
              disabled={summaryBusy}
              className="rounded-md border px-3 py-1.5 disabled:opacity-50"
              style={btn}
            >
              {summaryBusy ? 'Thinking…' : summary?.text ? 'Regenerate' : 'Generate review'}
            </button>
          </div>
        </div>
        {summaryError && <p className="mt-2 text-sm">{summaryError}</p>}
        {summary?.text ? (
          <p className="secondary mt-3 whitespace-pre-wrap text-sm leading-relaxed">{summary.text}</p>
        ) : (
          !summaryError && (
            <p className="muted mt-2 text-sm">
              No review yet this week. It reads your recent Whoop and Garmin data, your goal, and last
              week&apos;s recommendations.
            </p>
          )
        )}
        {thisWeekNote && (
          <p className="muted mt-3 text-xs">
            Saved for next review ({thisWeekNote.week_key}): {thisWeekNote.text}
          </p>
        )}
      </section>

      <section className="card">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold">Ask your coach</h2>
          {msgs.length > 0 && (
            <button onClick={clearChat} className="muted text-sm underline">
              Clear chat
            </button>
          )}
        </div>
        <div className="mt-3 max-h-[28rem] space-y-3 overflow-y-auto">
          {msgs.length === 0 && (
            <div className="flex flex-wrap gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => ask(s)}
                  className="rounded-md border px-3 py-1.5 text-left text-sm"
                  style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
                >
                  {s}
                </button>
              ))}
            </div>
          )}
          {msgs.map((m, i) => (
            <div key={i} className={m.role === 'user' ? 'flex justify-end' : 'flex'}>
              <div
                className="max-w-[85%] whitespace-pre-wrap rounded-lg px-3 py-2 text-sm leading-relaxed"
                style={{
                  background: m.role === 'user' ? 'var(--text-primary)' : 'var(--surface-0)',
                  color: m.role === 'user' ? 'var(--surface-1)' : 'var(--text-primary)',
                  border: m.role === 'user' ? 'none' : '1px solid var(--border)',
                }}
              >
                {m.content}
              </div>
            </div>
          ))}
          {chatBusy && <p className="muted text-sm">Thinking…</p>}
          {chatError && <p className="text-sm">{chatError}</p>}
          <div ref={endRef} />
        </div>
        <form
          className="mt-3 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            void ask(input)
          }}
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about training, recovery, sleep…"
            aria-label="Message to coach"
            className="min-w-0 flex-1 rounded-md border px-3 py-2 text-sm"
            style={field}
          />
          <button
            type="submit"
            disabled={chatBusy || !input.trim()}
            className="rounded-md border px-4 py-2 text-sm disabled:opacity-50"
            style={btn}
          >
            Send
          </button>
        </form>
        <p className="muted mt-2 text-xs">
          The chat is saved and the coach remembers it. General fitness guidance, not medical advice.
        </p>
      </section>

      <ProfileForm onSaved={loadAll} />
    </div>
  )
}
