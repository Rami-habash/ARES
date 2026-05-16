import { API_BASE } from '@/lib/config'
import type { GymSession } from '@/hooks/useGymSessions'

export interface SessionReport {
  patient_id: string
  report:     string
}

async function postJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { method: 'POST' })
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`)
  return res.json() as Promise<T>
}

export function leaveSession(sessionId: number): Promise<GymSession> {
  return postJson<GymSession>(`/gym/${sessionId}/leave`)
}

export function stillHere(sessionId: number): Promise<GymSession> {
  return postJson<GymSession>(`/gym/${sessionId}/still_here`)
}

export function endSessionAndReport(sessionId: number): Promise<SessionReport> {
  return postJson<SessionReport>(`/gym/${sessionId}/report`)
}
