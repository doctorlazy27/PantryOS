import { useCallback, useEffect, useRef, useState } from 'react'

const DEFAULT_INTERVAL = 5000

export function useLiveRefresh(load: () => Promise<void>, intervalMs = DEFAULT_INTERVAL) {
  const loadRef = useRef(load)
  const inFlight = useRef(false)
  const [initialLoading, setInitialLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)

  useEffect(() => { loadRef.current = load }, [load])

  const refresh = useCallback(async () => {
    if (inFlight.current) return
    inFlight.current = true
    setRefreshing(true)
    try {
      await loadRef.current()
    } finally {
      inFlight.current = false
      setInitialLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    const refreshWhenVisible = () => {
      if (document.visibilityState === 'visible') void refresh()
    }

    void refresh()
    const timer = window.setInterval(refreshWhenVisible, intervalMs)
    window.addEventListener('focus', refreshWhenVisible)
    window.addEventListener('online', refreshWhenVisible)
    document.addEventListener('visibilitychange', refreshWhenVisible)

    return () => {
      window.clearInterval(timer)
      window.removeEventListener('focus', refreshWhenVisible)
      window.removeEventListener('online', refreshWhenVisible)
      document.removeEventListener('visibilitychange', refreshWhenVisible)
    }
  }, [intervalMs, refresh])

  return { initialLoading, refreshing, refresh }
}