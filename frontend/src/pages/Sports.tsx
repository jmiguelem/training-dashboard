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
import { ChartCard, Loading, Stat, tooltipStyle } from '../components/ui'
import { shortDate } from '../lib/format'
import { useApi } from '../lib/useApi'

type Zones = Record<'z1' | 'z2' | 'z3' | 'z4' | 'z5', number>
type Act = {
  id: number
  date: string
  name: string | null
  km: number
  minutes: number
  avg_hr: number | null
  zones: Zones
  aerobic_te: number | null
  te_label: string | null
  training_load: number | null
  fade_pct: number | null
  [k: string]: number | string | null | Zones
}
type Week = { week: string; sessions: number; km: number; zone_minutes: Zones; easy_pct: number | null; hard_pct: number | null }
type SportData = {
  activities: Act[]
  weekly: Week[]
  last_4_weeks: { sessions: number; km: number; easy_pct: number | null; hard_pct: number | null }
}
type Data = Record<'Run' | 'Swim' | 'Bike', SportData>

const SPORTS = ['Run', 'Swim', 'Bike'] as const
const ZONE_KEYS = ['z1', 'z2', 'z3', 'z4', 'z5'] as const

const mmss = (s: number | null | undefined) =>
  s == null ? '-' : `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}`
const num = (v: unknown, d = 0) => (typeof v === 'number' ? v.toFixed(d) : '-')

function series(acts: Act[], key: string, label: string) {
  return acts
    .filter((a) => typeof a[key] === 'number')
    .map((a) => ({ date: shortDate(a.date + 'T12:00:00'), [label]: a[key] as number }))
}

function LineCard({
  title,
  subtitle,
  rows,
  label,
  color = 'var(--series-1)',
  fmt,
  domain,
}: {
  title: string
  subtitle: string
  rows: Record<string, string | number>[]
  label: string
  color?: string
  fmt?: (n: number) => string
  domain?: [number | string, number | string]
}) {
  return (
    <ChartCard title={title} subtitle={subtitle}>
      {rows.length < 2 ? (
        <p className="muted text-sm">Needs at least two sessions with this metric.</p>
      ) : (
        <ResponsiveContainer>
          <LineChart data={rows}>
            <CartesianGrid vertical={false} />
            <XAxis dataKey="date" minTickGap={24} tickLine={false} />
            <YAxis
              width={44}
              tickLine={false}
              axisLine={false}
              domain={domain ?? ['auto', 'auto']}
              tickFormatter={fmt}
            />
            <Tooltip {...tooltipStyle} formatter={(v) => (fmt ? fmt(Number(v)) : String(v))} />
            <Line
              dataKey={label}
              stroke={color}
              strokeWidth={2}
              dot={{ r: 4, stroke: 'var(--surface-1)', strokeWidth: 2 }}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </ChartCard>
  )
}

function ZoneChart({ weekly }: { weekly: Week[] }) {
  const rows = weekly.map((w) => ({
    week: shortDate(w.week + 'T12:00:00'),
    ...Object.fromEntries(ZONE_KEYS.map((z) => [z.toUpperCase(), w.zone_minutes[z]])),
  }))
  return (
    <ChartCard
      title="Time in heart rate zones"
      subtitle="Minutes per week. Zones come from your Garmin watch settings."
    >
      <ResponsiveContainer>
        <BarChart data={rows}>
          <CartesianGrid vertical={false} />
          <XAxis dataKey="week" minTickGap={24} tickLine={false} />
          <YAxis width={36} tickLine={false} axisLine={false} />
          <Tooltip {...tooltipStyle} />
          <Legend iconType="square" />
          {ZONE_KEYS.map((z, i) => (
            <Bar
              key={z}
              dataKey={z.toUpperCase()}
              stackId="z"
              fill={`var(--zone-${i + 1})`}
              stroke="var(--surface-1)"
              strokeWidth={2}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  )
}

function Table({ sport, acts }: { sport: 'Run' | 'Swim'; acts: Act[] }) {
  const cols: [string, (a: Act) => string][] =
    sport === 'Run'
      ? [
          ['Pace /km', (a) => mmss(a.pace_s_per_km as number)],
          ['Cadence', (a) => num(a.cadence_spm)],
          ['Stride m', (a) => num(a.stride_m, 2)],
          ['GCT ms', (a) => num(a.ground_contact_ms)],
          ['Vert ratio', (a) => num(a.vertical_ratio, 1)],
          ['Elev m', (a) => num(a.elevation_gain_m)],
        ]
      : [
          ['Pace /100m', (a) => mmss(a.pace_s_per_100m as number)],
          ['SWOLF', (a) => num(a.swolf)],
          ['Strokes/len', (a) => num(a.strokes_per_length, 1)],
          ['Stroke rate', (a) => num(a.stroke_rate_spm)],
          ['Rest %', (a) => num(a.rest_share_pct)],
        ]
  const head = ['Date', 'km', 'Min', 'Avg HR', ...cols.map((c) => c[0]), 'Fade %', 'Effect', 'Load']
  return (
    <div className="card overflow-x-auto p-0">
      <table className="w-full text-left text-sm tabular-nums">
        <thead className="muted text-xs uppercase">
          <tr>
            {head.map((h) => (
              <th key={h} className="whitespace-nowrap px-3 py-2 font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {acts
            .slice()
            .reverse()
            .map((a) => (
              <tr key={a.id} style={{ borderTop: '1px solid var(--border)' }}>
                <td className="whitespace-nowrap px-3 py-2">{shortDate(a.date + 'T12:00:00')}</td>
                <td className="px-3 py-2">{a.km.toFixed(2)}</td>
                <td className="px-3 py-2">{a.minutes}</td>
                <td className="px-3 py-2">{a.avg_hr ?? '-'}</td>
                {cols.map(([h, f]) => (
                  <td key={h} className="px-3 py-2">
                    {f(a)}
                  </td>
                ))}
                <td className="px-3 py-2">{a.fade_pct ?? '-'}</td>
                <td className="whitespace-nowrap px-3 py-2">
                  {a.aerobic_te ?? '-'}
                  {a.te_label ? ` ${a.te_label.toLowerCase().replace(/_/g, ' ')}` : ''}
                </td>
                <td className="px-3 py-2">{a.training_load ?? '-'}</td>
              </tr>
            ))}
        </tbody>
      </table>
    </div>
  )
}

export default function Sports({ reloadKey }: { reloadKey: number }) {
  const [sport, setSport] = useState<(typeof SPORTS)[number]>('Run')
  const { data, error, loading } = useApi<Data>('/api/sport-metrics?days=365', reloadKey)
  const d = data?.[sport]
  const acts = d?.activities ?? []
  const last = d?.last_4_weeks
  const charts = useMemo(() => {
    if (sport === 'Run')
      return [
        { title: 'Pace', subtitle: 'min/km, lower is faster', key: 'pace_s_per_km', label: 'Pace', fmt: mmss, color: 'var(--series-1)' },
        { title: 'Cadence', subtitle: 'Steps per minute. Most runners settle near 160-180 as they get fitter.', key: 'cadence_spm', label: 'Cadence', color: 'var(--series-3)' },
        { title: 'Ground contact time', subtitle: 'Milliseconds per step, lower is usually more efficient', key: 'ground_contact_ms', label: 'GCT', color: 'var(--series-2)' },
        { title: 'Stride length', subtitle: 'Metres per step', key: 'stride_m', label: 'Stride', color: 'var(--series-4)' },
      ]
    if (sport === 'Swim')
      return [
        { title: 'Pace per 100 m', subtitle: 'min:sec, lower is faster (moving time)', key: 'pace_s_per_100m', label: 'Pace', fmt: mmss, color: 'var(--series-1)' },
        { title: 'SWOLF', subtitle: 'Strokes plus seconds per length, lower is more efficient', key: 'swolf', label: 'SWOLF', color: 'var(--series-3)' },
        { title: 'Strokes per length', subtitle: 'Fewer at the same pace means better stroke efficiency', key: 'strokes_per_length', label: 'Strokes', color: 'var(--series-2)' },
        { title: 'Rest share', subtitle: 'Percent of the session spent resting at the wall', key: 'rest_share_pct', label: 'Rest %', color: 'var(--series-4)' },
      ]
    return []
  }, [sport])

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Sports</h1>
        <div role="group" aria-label="Sport" className="flex gap-1">
          {SPORTS.map((s) => (
            <button
              key={s}
              onClick={() => setSport(s)}
              aria-pressed={sport === s}
              className="rounded-md border px-3 py-1 text-sm"
              style={{
                borderColor: 'var(--border)',
                background: sport === s ? 'var(--text-primary)' : 'var(--surface-1)',
                color: sport === s ? 'var(--surface-1)' : 'var(--text-secondary)',
              }}
            >
              {s}
            </button>
          ))}
        </div>
      </div>
      <Loading error={error} loading={loading && !data} />
      {data && acts.length === 0 && (
        <p className="muted text-sm">
          No {sport.toLowerCase()} sessions found
          {sport === 'Bike' ? '. Garmin has no cycling activities for you yet.' : '.'}
        </p>
      )}
      {data && acts.length > 0 && last && (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <Stat label="Sessions (4 weeks)" value={last.sessions} sub={`${last.km} km`} />
            <Stat
              label="Easy time (Z1-2)"
              value={last.easy_pct != null ? `${last.easy_pct}%` : '-'}
              sub="Of time in zones, last 4 weeks"
            />
            <Stat
              label="Hard time (Z4-5)"
              value={last.hard_pct != null ? `${last.hard_pct}%` : '-'}
              sub="Of time in zones, last 4 weeks"
            />
            <Stat label="Sessions (all)" value={acts.length} sub="Last 12 months" />
          </div>
          <ZoneChart weekly={d!.weekly} />
          <div className="grid gap-4 lg:grid-cols-2">
            {charts.map((c) => (
              <LineCard
                key={c.key}
                title={c.title}
                subtitle={c.subtitle}
                rows={series(acts, c.key, c.label)}
                label={c.label}
                color={c.color}
                fmt={c.fmt}
              />
            ))}
          </div>
          {sport !== 'Bike' && <Table sport={sport} acts={acts} />}
          <p className="muted text-xs">
            Fade % is the speed change from the first to the second half of a session (negative means
            you slowed down). Effect is Garmin&apos;s aerobic training effect.
          </p>
        </>
      )}
    </div>
  )
}
