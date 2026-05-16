'use client'
import { useEffect, useState } from 'react'
import { API_BASE } from '@/lib/config'

export interface GymSession {
  id:          number
  patient_id:  string
  state:       'CHECKING_IN' | 'ACTIVE' | 'LOST' | 'LEFT'
  started_at:  string
  ended_at:    string | null
  last_event:  string | null
  marker_url:  string | null
}

// Polls /gym every `intervalMs` to surface live presence in the room.
// Polling (vs. WebSocket) is fine here — state changes are coarse (a few per
// minute) and we already have the per-frame stream for visual feedback.
export function useGymSessions(intervalMs: number = 1500) {
  const [sessions, setSessions] = useState<GymSession[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let stopped = false
    const tick = async () => {
      try {
        const r = await fetch(`${API_BASE}/gym`)
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        const data: GymSession[] = await r.json()
        if (!stopped) {
          setSessions(data)
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
  }, [intervalMs])

  return { sessions, error }
}
