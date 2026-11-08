export type Recovery = {
  cycle_id: number
  created_at: string
  recovery_score: number | null
  resting_hr: number | null
  hrv_rmssd_ms: number | null
  spo2: number | null
  skin_temp_c: number | null
}
export type Sleep = {
  id: string
  start: string
  end: string
  nap: number
  performance_pct: number | null
  efficiency_pct: number | null
  respiratory_rate: number | null
  light_ms: number | null
  sws_ms: number | null
  rem_ms: number | null
  awake_ms: number | null
  in_bed_ms: number | null
  disturbances: number | null
}
export type Cycle = {
  id: number
  start: string
  end: string | null
  strain: number | null
  avg_hr: number | null
  max_hr: number | null
  kilojoule: number | null
}
export type Activity = {
  id: number
  name: string | null
  sport: string | null
  start: string
  distance_m: number | null
  duration_s: number | null
  avg_hr: number | null
  max_hr: number | null
  avg_speed_ms: number | null
  calories: number | null
  cadence: number | null
  avg_power: number | null
  elevation_gain_m: number | null
  vo2max: number | null
  aerobic_te: number | null
  training_load: number | null
}
export type GarminDaily = {
  date: string
  steps: number | null
  resting_hr: number | null
  body_battery_high: number | null
  body_battery_low: number | null
  avg_stress: number | null
  vo2max: number | null
}
export type SyncInfo = { status: string; finished_at: string | null; detail: string | null } | null
export type Status = {
  whoop_connected: boolean
  garmin_connected: boolean
  last_whoop_sync: SyncInfo
  last_garmin_sync: SyncInfo
  last_auto_run: SyncInfo
  next_auto_run: string | null
}

export async function get<T>(path: string): Promise<T> {
  const r = await fetch(path)
  if (!r.ok) throw new Error(`${path}: ${r.status}`)
  return r.json()
}

export async function post(path: string): Promise<void> {
  const r = await fetch(path, { method: 'POST' })
  if (!r.ok) {
    let msg = `${r.status}`
    try {
      msg = (await r.json()).detail ?? msg
    } catch {
      /* ignore */
    }
    throw new Error(msg)
  }
}
