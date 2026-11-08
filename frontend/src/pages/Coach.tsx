import { useEffect, useRef, useState } from 'react'

type Summary = { text: string | null; created_at?: string; cached?: boolean; model?: string }
type Msg = { role: 'user' | 'assistant'; content: string }

async function call<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(data.detail ?? `Request failed (${r.status})`)
  return data as T
}

const SUGGESTIONS = [
  'Should I run today?',
  'How is my running base progressing?',
  'Am I sleeping enough to recover from 4 gym days?',
]

export default function Coach({ reloadKey }: { reloadKey: number }) {
  const [summary, setSummary] = useState<Summary | null>(null)
  const [summaryBusy, setSummaryBusy] = useState(false)
  const [summaryError, setSummaryError] = useState<string | null>(null)
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [input, setInput] = useState('')
  const [chatBusy, setChatBusy] = useState(false)
  const [chatError, setChatError] = useState<string | null>(null)
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    void fetch('/api/coach/summary')
      .then((r) => r.json())
      .then(setSummary)
      .catch(() => setSummary(null))
  }, [reloadKey])
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'nearest' })
  }, [msgs, chatBusy])

  async function generate(force: boolean) {
    setSummaryBusy(true)
    setSummaryError(null)
    try {
      setSummary(await call<Summary>(`/api/coach/summary?force=${force}`, {}))
    } catch (e) {
      setSummaryError((e as Error).message)
    } finally {
      setSummaryBusy(false)
    }
  }

  async function send(text: string) {
    const t = text.trim()
    if (!t || chatBusy) return
    const next = [...msgs, { role: 'user' as const, content: t }]
    setMsgs(next)
    setInput('')
    setChatBusy(true)
    setChatError(null)
    try {
      const { reply } = await call<{ reply: string }>('/api/coach/chat', { messages: next })
      setMsgs([...next, { role: 'assistant', content: reply }])
    } catch (e) {
      setChatError((e as Error).message)
    } finally {
      setChatBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Coach</h1>

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
              style={{ borderColor: 'var(--border)', background: 'var(--surface-1)' }}
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
              No review yet this week. It reads your last weeks of Whoop and Garmin data.
            </p>
          )
        )}
      </section>

      <section className="card">
        <h2 className="text-base font-semibold">Ask your coach</h2>
        <div className="mt-3 max-h-[28rem] space-y-3 overflow-y-auto">
          {msgs.length === 0 && (
            <div className="flex flex-wrap gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
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
            send(input)
          }}
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about training, recovery, sleep…"
            aria-label="Message to coach"
            className="min-w-0 flex-1 rounded-md border px-3 py-2 text-sm"
            style={{
              borderColor: 'var(--border)',
              background: 'var(--surface-0)',
              color: 'var(--text-primary)',
            }}
          />
          <button
            type="submit"
            disabled={chatBusy || !input.trim()}
            className="rounded-md border px-4 py-2 text-sm disabled:opacity-50"
            style={{ borderColor: 'var(--border)', background: 'var(--surface-1)' }}
          >
            Send
          </button>
        </form>
        <p className="muted mt-2 text-xs">
          Answers use your synced data. General fitness guidance, not medical advice.
        </p>
      </section>
    </div>
  )
}
