'use client'
import { useEffect, useState } from 'react'
import { API_BASE } from '@/lib/config'
import type { GymSession } from './useGymSessions'

// Single-session polling — drives the patient-facing screens. Returns null
// while loading; returns {error} if the backend says the session is gone.
export function useGymSession(sessionId: number | null, intervalMs: number = 1000) {
  const [session, setSession] = useState<GymSession | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (sessionId === null) return
    let stopped = false
    const tick = async () => {
      try {
        const r = await fetch(`${API_BASE}/gym/${sessionId}`)
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        const data: GymSession = await r.json()
        if (!stopped) {
          setSession(data)
          setError(null)
        }
      } catch (exc) {
        if (!stopped) setError((exc as Error).message)
      }
    }
    tick()
    const id = setInterval(tick, intervalMs)
    return () => {
      stopped = true
      clearInterval(id)
    }
  }, [sessionId, intervalMs])

  return { session, error }
}
