import { API_BASE, USE_MOCK } from '@/lib/config'
import { MOCK_PATIENTS } from '@/data/patients'
import { authHeaders } from '@/lib/api/auth'
import type { Patient } from '@/types'

// Transform the backend patient shape → frontend Patient type
function adaptPatient(raw: Record<string, unknown>): Patient {
  return {
    id: raw.id as string,
    name: raw.name as string,
    age: raw.date_of_birth
      ? new Date().getFullYear() - new Date(raw.date_of_birth as string).getFullYear()
      : 0,
    zone: 'Room A',
    status: 'Stable',
    currentExercise: ((raw.assigned_exercises as string[]) ?? [])[0] ?? 'Rest',
    assignedExercises: (raw.assigned_exercises as string[]) ?? [],
    rehabPlan: (raw.notes as string) ?? '',
    formScore: (() => {
      const sessions = (raw.recent_sessions as Array<{ form_score: number | null }>) ?? []
      const latest = sessions.find(s => s.form_score != null)
      return latest ? Math.round(latest.form_score!) : 0
    })(),
    riskScore: 'Low',
    adherence: 80,
    trackingConfidence: 90,
    restrictions: [],
    lastSession: (() => {
      const sessions = (raw.recent_sessions as Array<{ session_date: string }>) ?? []
      return sessions[0]?.session_date ?? ''
    })(),
    recentEvents: ((raw.alerts as Array<{ id: number; severity: string; title: string; created_at?: string; timestamp?: string }>) ?? [])
      .slice(0, 5)
      .map(a => ({
        id: String(a.id),
        time: a.timestamp ?? a.created_at ?? '',
        type: 'alert' as const,
        description: a.title,
      })),
  }
}

export async function getPatients(): Promise<Patient[]> {
  if (USE_MOCK) return MOCK_PATIENTS
  const res = await fetch(`${API_BASE}/patients`, { headers: authHeaders() })
  if (!res.ok) return []
  const data = await res.json()
  return (data.patients ?? []).filter(Boolean).map(adaptPatient)
}

export async function getPatient(id: string): Promise<Patient | undefined> {
  if (USE_MOCK) return MOCK_PATIENTS.find(p => p.id === id)
  const res = await fetch(`${API_BASE}/patients/${id}`, { headers: authHeaders() })
  if (!res.ok) return undefined
  return adaptPatient(await res.json())
}

export async function getMyProfile(): Promise<Patient | undefined> {
  if (USE_MOCK) return MOCK_PATIENTS[0]
  const res = await fetch(`${API_BASE}/patients/me`, { headers: authHeaders() })
  if (!res.ok) return undefined
  return adaptPatient(await res.json())
}

export async function assignExercises(patientId: string, exercises: string[]): Promise<void> {
  if (USE_MOCK) return
  await fetch(`${API_BASE}/patients/${patientId}/exercises`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ exercises }),
  })
}
