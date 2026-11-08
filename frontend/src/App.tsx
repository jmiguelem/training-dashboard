import { useCallback, useEffect, useState } from 'react'
import { NavLink, Route, Routes } from 'react-router-dom'
import { get, post, type Status } from './api'
import Activities from './pages/Activities'
import Progress from './pages/Progress'
import Recovery from './pages/Recovery'
import Today from './pages/Today'

const NAV = [
  { to: '/', label: 'Today' },
  { to: '/activities', label: 'Activities' },
  { to: '/recovery', label: 'Recovery' },
  { to: '/progress', label: 'Progress' },
]

export default function App() {
  const [status, setStatus] = useState<Status | null>(null)
  const [reloadKey, setReloadKey] = useState(0)
  const [syncing, setSyncing] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  const loadStatus = useCallback(() => {
    get<Status>('/api/status').then(setStatus).catch(() => setStatus(null))
  }, [])
  useEffect(loadStatus, [loadStatus, reloadKey])

  async function syncAll() {
    setSyncing(true)
    setMessage(null)
    const errors: string[] = []
    for (const [name, path, connected] of [
      ['Whoop', '/api/sync/whoop', status?.whoop_connected],
      ['Garmin', '/api/sync/garmin', status?.garmin_connected],
    ] as const) {
      if (!connected) continue
      try {
        await post(path)
      } catch (e) {
        errors.push(`${name}: ${(e as Error).message}`)
      }
    }
    setSyncing(false)
    setMessage(errors.length ? errors.join(' | ') : 'Synced')
    setReloadKey((k) => k + 1)
  }

  const lastSync = [status?.last_whoop_sync, status?.last_garmin_sync]
    .map((s) => s?.finished_at)
    .filter((x): x is string => !!x)
    .sort()
    .pop()

  return (
    <div className="mx-auto max-w-6xl px-4 pb-12">
      <header className="flex flex-wrap items-center justify-between gap-3 py-4">
        <nav className="flex gap-1" aria-label="Main">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.to === '/'}
              className="rounded-md px-3 py-1.5 text-sm"
              style={({ isActive }) => ({
                background: isActive ? 'var(--text-primary)' : 'transparent',
                color: isActive ? 'var(--surface-1)' : 'var(--text-secondary)',
              })}
            >
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="flex items-center gap-3 text-sm">
          {status && !status.whoop_connected && (
            <a className="underline" href="/auth/whoop/login">
              Connect Whoop
            </a>
          )}
          {status && !status.garmin_connected && (
            <span className="muted">Garmin: run login command</span>
          )}
          <span className="muted">
            {message ??
              (lastSync
                ? `Synced ${new Date(lastSync).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}`
                : 'Not synced')}
          </span>
          <button
            onClick={syncAll}
            disabled={syncing}
            className="rounded-md border px-3 py-1.5 disabled:opacity-50"
            style={{ borderColor: 'var(--border)', background: 'var(--surface-1)' }}
          >
            {syncing ? 'Syncing…' : 'Sync now'}
          </button>
        </div>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Today reloadKey={reloadKey} />} />
          <Route path="/activities" element={<Activities reloadKey={reloadKey} />} />
          <Route path="/recovery" element={<Recovery reloadKey={reloadKey} />} />
          <Route path="/progress" element={<Progress reloadKey={reloadKey} />} />
        </Routes>
      </main>
    </div>
  )
}
