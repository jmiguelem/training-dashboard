import { useState } from 'react'

export default function Login({ onLogin }: { onLogin: () => void }) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const r = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password }),
      })
      if (r.ok) return onLogin()
      const data = await r.json().catch(() => ({}))
      setError(data.detail ?? `Login failed (${r.status})`)
    } catch {
      setError('Cannot reach the server')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-sm items-center px-4">
      <form onSubmit={submit} className="w-full space-y-3">
        <h1 className="text-lg font-semibold">Training Dashboard</h1>
        <input
          type="password"
          autoFocus
          autoComplete="current-password"
          aria-label="Password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full rounded-md border px-3 py-2"
          style={{ borderColor: 'var(--border)', background: 'var(--surface-1)', color: 'var(--text-primary)' }}
        />
        {error && <p role="alert" className="text-sm">{error}</p>}
        <button
          disabled={busy || !password}
          className="w-full rounded-md border px-3 py-2 disabled:opacity-50"
          style={{ borderColor: 'var(--border)', background: 'var(--surface-1)' }}
        >
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </div>
  )
}
