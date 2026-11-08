import { useState } from 'react'
import type { Activity } from '../api'
import { Loading, RangePicker } from '../components/ui'
import {
  fmtDuration,
  fmtKm,
  fmtPace,
  parseTs,
  sportGroup,
  sportLabel,
  type SportGroup,
} from '../lib/format'
import { useApi } from '../lib/useApi'

const FILTERS: ('All' | SportGroup)[] = ['All', 'Run', 'Swim', 'Bike', 'Strength', 'Other']

export default function Activities({ reloadKey }: { reloadKey: number }) {
  const [days, setDays] = useState(90)
  const [filter, setFilter] = useState<'All' | SportGroup>('All')
  const { data, error, loading } = useApi<Activity[]>(`/api/activities?days=${days}`, reloadKey)
  const rows = (data ?? [])
    .filter((a) => filter === 'All' || sportGroup(a.sport) === filter)
    .slice()
    .reverse()

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Activities</h1>
        <RangePicker value={days} onChange={setDays} />
      </div>
      <div role="group" aria-label="Sport" className="flex flex-wrap gap-1">
        {FILTERS.map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            aria-pressed={filter === f}
            className="rounded-md border px-3 py-1 text-sm"
            style={{
              borderColor: 'var(--border)',
              background: filter === f ? 'var(--text-primary)' : 'var(--surface-1)',
              color: filter === f ? 'var(--surface-1)' : 'var(--text-secondary)',
            }}
          >
            {f}
          </button>
        ))}
      </div>
      <Loading error={error} loading={loading && !data} />
      <div className="card overflow-x-auto p-0">
        <table className="w-full text-left text-sm tabular-nums">
          <thead className="muted text-xs uppercase">
            <tr>
              {['Date', 'Activity', 'Type', 'Distance', 'Time', 'Pace', 'Avg HR', 'Load'].map((h) => (
                <th key={h} className="px-3 py-2 font-medium">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((a) => {
              const g = sportGroup(a.sport)
              return (
                <tr key={a.id} style={{ borderTop: '1px solid var(--border)' }}>
                  <td className="px-3 py-2">
                    {parseTs(a.start).toLocaleDateString(undefined, {
                      month: 'short',
                      day: 'numeric',
                    })}
                  </td>
                  <td className="px-3 py-2">{a.name ?? '-'}</td>
                  <td className="px-3 py-2">{sportLabel(a.sport)}</td>
                  <td className="px-3 py-2">{fmtKm(a.distance_m)}</td>
                  <td className="px-3 py-2">{fmtDuration(a.duration_s)}</td>
                  <td className="px-3 py-2">{g === 'Run' ? fmtPace(a.avg_speed_ms) : '-'}</td>
                  <td className="px-3 py-2">{a.avg_hr ? Math.round(a.avg_hr) : '-'}</td>
                  <td className="px-3 py-2">{a.training_load ? Math.round(a.training_load) : '-'}</td>
                </tr>
              )
            })}
            {rows.length === 0 && !loading && (
              <tr>
                <td colSpan={8} className="muted px-3 py-6 text-center">
                  No activities in this range.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
