import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { shortDate } from '../lib/format'
import { useApi } from '../lib/useApi'
import { ChartCard, Loading, tooltipStyle } from './ui'

type Night = { date: string; bed: string; wake: string; bed_min: number; wake_min: number; asleep_h: number | null }
type Stats = {
  nights: number
  avg_bed?: string
  avg_wake?: string
  bed_sd_min?: number
  wake_sd_min?: number
  avg_asleep_h?: number
  weekday_bed?: string
  weekend_bed?: string
  weekday_wake?: string
  weekend_wake?: string
}
type Data = {
  nights: { date: string; whoop: Night | null; garmin: Night | null }[]
  stats: { whoop: Stats; garmin: Stats }
}

const clock = (m: number) => {
  const x = Math.round(m) % 1440
  const h = Math.floor(x / 60)
  const mm = String(x % 60).padStart(2, '0')
  return `${((h + 11) % 12) + 1}:${mm} ${h < 12 ? 'AM' : 'PM'}`
}

function StatsCard({ name, color, s }: { name: string; color: string; s: Stats }) {
  return (
    <div className="card">
      <div className="flex items-center gap-2 text-sm font-semibold">
        <span aria-hidden className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: color }} />
        {name}
        <span className="muted font-normal">· {s.nights} nights</span>
      </div>
      {s.nights === 0 ? (
        <p className="muted mt-2 text-sm">No data yet. Press Sync now.</p>
      ) : (
        <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
          <div>
            <dt className="muted text-xs uppercase">Bedtime</dt>
            <dd className="text-lg font-semibold tabular-nums">{s.avg_bed}</dd>
            <dd className="secondary text-xs">varies ±{s.bed_sd_min} min</dd>
          </div>
          <div>
            <dt className="muted text-xs uppercase">Wake up</dt>
            <dd className="text-lg font-semibold tabular-nums">{s.avg_wake}</dd>
            <dd className="secondary text-xs">varies ±{s.wake_sd_min} min</dd>
          </div>
          <div>
            <dt className="muted text-xs uppercase">Asleep</dt>
            <dd className="text-lg font-semibold tabular-nums">{s.avg_asleep_h} h</dd>
            <dd className="secondary text-xs">average per night</dd>
          </div>
          <div>
            <dt className="muted text-xs uppercase">Weekdays / weekends</dt>
            <dd className="secondary tabular-nums">
              Bed {s.weekday_bed ?? '-'} / {s.weekend_bed ?? '-'}
            </dd>
            <dd className="secondary tabular-nums">
              Wake {s.weekday_wake ?? '-'} / {s.weekend_wake ?? '-'}
            </dd>
          </div>
        </dl>
      )}
    </div>
  )
}

function TimeChart({
  title,
  subtitle,
  rows,
  tickMode,
}: {
  title: string
  subtitle: string
  rows: Record<string, string | number | null>[]
  tickMode: 'bed' | 'wake'
}) {
  const vals = rows.flatMap((r) => [r.Whoop, r.Garmin]).filter((v): v is number => typeof v === 'number')
  // Trim rare outliers (an all-nighter, a late sleep) so they do not squash the typical range.
  const sorted = [...vals].sort((a, b) => a - b)
  const q = (p: number) => sorted[Math.min(sorted.length - 1, Math.max(0, Math.round(p * (sorted.length - 1))))] ?? 0
  const lo = Math.floor((q(0.03) - 30) / 60) * 60
  const hi = Math.ceil((q(0.97) + 30) / 60) * 60
  const ticks: number[] = []
  for (let t = lo; t <= hi; t += 60) ticks.push(t)
  return (
    <ChartCard title={title} subtitle={subtitle}>
      <ResponsiveContainer>
        <LineChart data={rows}>
          <CartesianGrid vertical={false} />
          <XAxis dataKey="date" minTickGap={32} tickLine={false} />
          <YAxis
            width={64}
            tickLine={false}
            axisLine={false}
            domain={[lo, hi]}
            ticks={ticks}
            allowDataOverflow
            tickFormatter={clock}
          />
          <Tooltip {...tooltipStyle} formatter={(v) => (typeof v === 'number' ? clock(v) : String(v))} />
          <Legend iconType="plainline" />
          <Line dataKey="Whoop" stroke="var(--series-1)" strokeWidth={2} dot={false} connectNulls={false} />
          <Line
            dataKey="Garmin"
            stroke="var(--series-2)"
            strokeWidth={2}
            strokeDasharray="5 3"
            dot={false}
            connectNulls={false}
          />
        </LineChart>
      </ResponsiveContainer>
      <span className="sr-only">{tickMode === 'bed' ? 'Bedtime by night' : 'Wake time by night'}</span>
    </ChartCard>
  )
}

export default function SleepSchedule({ reloadKey }: { reloadKey: number }) {
  const { data, error, loading } = useApi<Data>('/api/sleep-schedule?days=90', reloadKey)
  const rows = (data?.nights ?? []).map((n) => ({
    date: shortDate(n.date + 'T12:00:00'),
    bed: { Whoop: n.whoop?.bed_min ?? null, Garmin: n.garmin?.bed_min ?? null },
    wake: { Whoop: n.whoop?.wake_min ?? null, Garmin: n.garmin?.wake_min ?? null },
  }))
  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">Sleep schedule</h2>
        <p className="secondary text-sm">
          Bedtime and wake-up time per night, last 3 months, local clock time. Whoop and Garmin detect
          sleep differently, so they can disagree by 10-30 minutes or more.
        </p>
      </div>
      <Loading error={error} loading={loading && !data} />
      {data && (
        <>
          <div className="grid gap-4 md:grid-cols-2">
            <StatsCard name="Whoop" color="var(--series-1)" s={data.stats.whoop} />
            <StatsCard name="Garmin" color="var(--series-2)" s={data.stats.garmin} />
          </div>
          {rows.length > 1 && (
            <div className="grid gap-4 lg:grid-cols-2">
              <TimeChart
                title="Bedtime"
                subtitle="When you fell asleep, per night"
                tickMode="bed"
                rows={rows.map((r) => ({ date: r.date, ...r.bed }))}
              />
              <TimeChart
                title="Wake-up time"
                subtitle="When you woke up, per night"
                tickMode="wake"
                rows={rows.map((r) => ({ date: r.date, ...r.wake }))}
              />
            </div>
          )}
        </>
      )}
    </section>
  )
}
