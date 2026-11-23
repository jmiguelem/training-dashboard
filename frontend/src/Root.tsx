import { useEffect, useState } from 'react'
import App from './App'
import Login from './Login'

// Any 401 from our own API (expired or missing session) sends the user back to the login screen.
const realFetch = window.fetch.bind(window)
window.fetch = async (...args) => {
  const res = await realFetch(...args)
  const url = typeof args[0] === 'string' ? args[0] : args[0] instanceof Request ? args[0].url : String(args[0])
  if (res.status === 401 && url.includes('/api/') && !url.includes('/api/auth/')) {
    window.dispatchEvent(new Event('unauthorized'))
  }
  return res
}

export default function Root() {
  const [authed, setAuthed] = useState<boolean | null>(null)

  useEffect(() => {
    realFetch('/api/auth/session')
      .then((r) => r.json())
      .then((d) => setAuthed(!!d.authenticated))
      .catch(() => setAuthed(false))
    const onUnauthorized = () => setAuthed(false)
    window.addEventListener('unauthorized', onUnauthorized)
    return () => window.removeEventListener('unauthorized', onUnauthorized)
  }, [])

  if (authed === null) return null
  if (!authed) return <Login onLogin={() => setAuthed(true)} />
  return (
    <>
      <App />
      <button
        className="fixed bottom-3 right-3 text-xs underline muted"
        onClick={() => fetch('/api/auth/logout', { method: 'POST' }).then(() => setAuthed(false))}
      >
        Sign out
      </button>
    </>
  )
}
