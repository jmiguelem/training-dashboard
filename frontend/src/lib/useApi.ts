import { useCallback, useEffect, useState } from 'react'
import { get } from '../api'

export function useApi<T>(path: string, reloadKey = 0) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const load = useCallback(() => {
    setLoading(true)
    get<T>(path)
      .then((d) => {
        setData(d)
        setError(null)
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [path])
  useEffect(load, [load, reloadKey])
  return { data, error, loading }
}
