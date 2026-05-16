import { API_BASE, USE_MOCK } from '@/lib/config'
import { authHeaders } from '@/lib/api/auth'

export interface SessionLog {
  id: number
  patient_id: string
  session_date: string
  exercises: string[]
  form_score: number | null
  summary: string
  created_at: string
}

const MOCK_SESSIONS: SessionLog[] = [
  {
    id: 1,
    patient_id: 'P001',
    session_date: '2024-01-15',
    exercises: ['squat', 'leg extension', 'hip thrust'],
    form_score: 76,
    summary: 'Good session overall. Knee valgus flagged on squat descent.',
    created_at: '2024-01-15T10:00:00Z',
  },
  {
    id: 2,
    patient_id: 'P002',
    session_date: '2024-01-14',
    exercises: ['shoulder press', 'lateral raise'],
    form_score: 68,
    summary: 'Scapular compensation noted. Reduce load on lateral raise.',
    created_at: '2024-01-14T14:00:00Z',
  },
]

export async function getSessions(patientId?: string): Promise<SessionLog[]> {
  if (USE_MOCK) {
    return patientId ? MOCK_SESSIONS.filter(s => s.patient_id === patientId) : MOCK_SESSIONS
  }
  const url = patientId
    ? `${API_BASE}/sessions?patient_id=${patientId}`
    : `${API_BASE}/sessions`
  const res = await fetch(url, { headers: authHeaders() })
  if (!res.ok) return []
  const data = await res.json()
  return data.sessions ?? []
}

export async function getMySessions(): Promise<SessionLog[]> {
  if (USE_MOCK) return MOCK_SESSIONS
  const res = await fetch(`${API_BASE}/sessions`, { headers: authHeaders() })
  if (!res.ok) return []
  const data = await res.json()
  return data.sessions ?? []
}
