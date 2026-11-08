import { useMemo, useState } from 'react'
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
import type { Activity } from '../api'
import { ChartCard, Loading, RangePicker, Stat, tooltipStyle } from '../components/ui'
import {
  dayKey,
  parseTs,
  shortDate,
  SPORT_COLORS,
  sportGroup,
  weekStart,
  type SportGroup,
} from '../lib/format'
import { useApi } from '../lib/useApi'

const GROUPS: SportGroup[] = ['Run', 'Swim', 'Bike', 'Strength', 'Other']

export default function Progress({ reloadKey }: { reloadKey: number }) {
  const [days, setDays] = useState(180)
  const { data, error, loading } = useApi<Activity[]>(`/api/activities?days=${days}`, reloadKey)

  const { weekly, efficiency, runWeekly, totals } = useMemo(() => {
    const acts = data ?? []
    const weeks = new Map<string, Record<string, number | string>>()
    const runWeeks = new Map<string, number>()
    for (const a of acts) {
      const d = parseTs(a.start)
      const wk = dayKey(weekStart(d))
      const g = sportGroup(a.sport)
      const row = weeks.get(wk) ?? { week: wk }
      row[g] = +(((row[g] as number) ?? 0) + (a.duration_s ?? 0) / 3600).toFixed(2)
      weeks.set(wk, row)
      if (g === 'Run') runWeeks.set(wk, (runWeeks.get(wk) ?? 0) + (a.distance_m ?? 0) / 1000)
    }
    const keys = [...weeks.keys()].sort()
    const weekly: Record<string, number | string>[] = keys.map((k) => ({
      ...weeks.get(k)!,
      label: shortDate(new Date(k + 'T00:00:00')),
    }))
    const runWeekly = keys.map((k) => ({
      label: shortDate(new Date(k + 'T00:00:00')),
      Distance: +(runWeeks.get(k) ?? 0).toFixed(2),
    }))
    // Aerobic efficiency: speed (m/min) per heartbeat-per-minute on runs of 10+ min.
    const efficiency = acts
      .filter(
        (a) =>
          sportGroup(a.sport) === 'Run' &&
          a.avg_hr &&
          a.avg_speed_ms &&
          (a.duration_s ?? 0) >= 600,
      )
      .map((a) => ({
        label: shortDate(a.start),
        Efficiency: +(((a.avg_speed_ms! * 60) / a.avg_hr!) as number).toFixed(3),
      }))
    const totals = {
      sessions: acts.length,
      runKm: acts
        .filter((a) => sportGroup(a.sport) === 'Run')
        .reduce((s, a) => s + (a.distance_m ?? 0), 0) / 1000,
      longestRun:
        Math.max(
          0,
          ...acts.filter((a) => sportGroup(a.sport) === 'Run').map((a) => a.distance_m ?? 0),
        ) / 1000,
      activeWeeks: keys.length,
    }
    return { weekly, efficiency, runWeekly, totals }
  }, [data])

  const present = GROUPS.filter((g) => weekly.some((w) => (w[g] as number) > 0))

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Progress</h1>
        <RangePicker value={days} onChange={setDays} options={[90, 180, 365]} />
      </div>
      <Loading error={error} loading={loading && !data} />
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Sessions" value={totals.sessions} sub={`${totals.activeWeeks} active weeks`} />
        <Stat label="Run distance" value={`${totals.runKm.toFixed(1)} km`} sub={`last ${days} days`} />
        <Stat label="Longest run" value={`${totals.longestRun.toFixed(1)} km`} />
        <Stat
          label="Sessions / week"
          value={totals.activeWeeks ? (totals.sessions / totals.activeWeeks).toFixed(1) : '-'}
        />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <ChartCard
          title="Weekly training time"
          subtitle="Hours per week by sport (weeks start Monday)"
        >
          <ResponsiveContainer>
            <BarChart data={weekly}>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="label" minTickGap={24} tickLine={false} />
              <YAxis width={32} tickLine={false} axisLine={false} />
              <Tooltip {...tooltipStyle} />
              <Legend iconType="square" />
              {present.map((g) => (
                <Bar
                  key={g}
                  dataKey={g}
                  stackId="w"
                  fill={SPORT_COLORS[g]}
                  stroke="var(--surface-1)"
                  strokeWidth={2}
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
        <ChartCard title="Weekly run distance" subtitle="Kilometres per week">
          <ResponsiveContainer>
            <BarChart data={runWeekly}>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="label" minTickGap={24} tickLine={false} />
              <YAxis width={32} tickLine={false} axisLine={false} />
              <Tooltip {...tooltipStyle} />
              <Bar dataKey="Distance" fill="var(--series-1)" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>
      <ChartCard
        title="Aerobic efficiency (runs)"
        subtitle="Metres per minute per heartbeat. Higher means faster at the same effort. Runs of 10+ minutes."
      >
        {efficiency.length < 2 ? (
          <p className="muted text-sm">Needs at least two runs of 10+ minutes with heart rate.</p>
        ) : (
          <ResponsiveContainer>
            <LineChart data={efficiency}>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="label" minTickGap={24} tickLine={false} />
              <YAxis width={40} tickLine={false} axisLine={false} domain={['auto', 'auto']} />
              <Tooltip {...tooltipStyle} />
              <Line
                dataKey="Efficiency"
                stroke="var(--series-1)"
                strokeWidth={2}
                dot={{ r: 4, stroke: 'var(--surface-1)', strokeWidth: 2 }}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </ChartCard>
    </div>
  )
}
