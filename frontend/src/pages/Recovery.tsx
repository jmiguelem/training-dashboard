import { useState } from 'react'
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
import type { Cycle, Recovery, Sleep } from '../api'
import { ChartCard, Loading, RangePicker, tooltipStyle } from '../components/ui'
import { hours, parseTs, shortDate } from '../lib/format'
import { useApi } from '../lib/useApi'

export default function RecoveryPage({ reloadKey }: { reloadKey: number }) {
  const [days, setDays] = useState(90)
  const rec = useApi<Recovery[]>(`/api/recovery?days=${days}`, reloadKey)
  const sleep = useApi<Sleep[]>(`/api/sleep?days=${days}`, reloadKey)
  const cycles = useApi<Cycle[]>(`/api/cycles?days=${days}`, reloadKey)

  const recRows = (rec.data ?? []).map((r) => ({
    date: shortDate(r.created_at),
    Recovery: r.recovery_score,
    HRV: r.hrv_rmssd_ms == null ? null : Math.round(r.hrv_rmssd_ms),
    'Resting HR': r.resting_hr,
  }))
  const sleepRows = (sleep.data ?? [])
    .filter((s) => !s.nap)
    .map((s) => ({
      date: shortDate(parseTs(s.end)),
      Light: +hours(s.light_ms).toFixed(2),
      Deep: +hours(s.sws_ms).toFixed(2),
      REM: +hours(s.rem_ms).toFixed(2),
    }))
  const strainRows = (cycles.data ?? []).map((c) => ({
    date: shortDate(c.start),
    Strain: c.strain,
  }))

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Recovery &amp; sleep</h1>
        <RangePicker value={days} onChange={setDays} />
      </div>
      <Loading error={rec.error ?? sleep.error} loading={rec.loading && !rec.data} />
      <div className="grid gap-4 lg:grid-cols-2">
        <ChartCard title="Recovery score" subtitle="Whoop, percent">
          <ResponsiveContainer>
            <LineChart data={recRows}>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="date" minTickGap={32} tickLine={false} />
              <YAxis domain={[0, 100]} width={32} tickLine={false} axisLine={false} />
              <Tooltip {...tooltipStyle} />
              <Line dataKey="Recovery" stroke="var(--series-1)" strokeWidth={2} dot={false} connectNulls />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
        <ChartCard title="Heart rate variability" subtitle="HRV (rmssd), ms">
          <ResponsiveContainer>
            <LineChart data={recRows}>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="date" minTickGap={32} tickLine={false} />
              <YAxis width={32} tickLine={false} axisLine={false} domain={['auto', 'auto']} />
              <Tooltip {...tooltipStyle} />
              <Line dataKey="HRV" stroke="var(--series-3)" strokeWidth={2} dot={false} connectNulls />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
        <ChartCard title="Resting heart rate" subtitle="bpm, lower is better">
          <ResponsiveContainer>
            <LineChart data={recRows}>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="date" minTickGap={32} tickLine={false} />
              <YAxis width={32} tickLine={false} axisLine={false} domain={['auto', 'auto']} />
              <Tooltip {...tooltipStyle} />
              <Line dataKey="Resting HR" stroke="var(--series-2)" strokeWidth={2} dot={false} connectNulls />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
        <ChartCard title="Day strain" subtitle="Whoop, 0-21">
          <ResponsiveContainer>
            <BarChart data={strainRows}>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="date" minTickGap={32} tickLine={false} />
              <YAxis domain={[0, 21]} width={32} tickLine={false} axisLine={false} />
              <Tooltip {...tooltipStyle} />
              <Bar dataKey="Strain" fill="var(--series-4)" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>
      <ChartCard title="Sleep by stage" subtitle="Hours per night, naps excluded">
        <ResponsiveContainer>
          <BarChart data={sleepRows}>
            <CartesianGrid vertical={false} />
            <XAxis dataKey="date" minTickGap={32} tickLine={false} />
            <YAxis width={32} tickLine={false} axisLine={false} />
            <Tooltip {...tooltipStyle} />
            <Legend iconType="square" />
            <Bar dataKey="Deep" stackId="s" fill="var(--series-1)" stroke="var(--surface-1)" strokeWidth={2} />
            <Bar dataKey="REM" stackId="s" fill="var(--series-2)" stroke="var(--surface-1)" strokeWidth={2} />
            <Bar dataKey="Light" stackId="s" fill="var(--series-3)" stroke="var(--surface-1)" strokeWidth={2} />
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>
    </div>
  )
}
