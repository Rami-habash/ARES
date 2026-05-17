'use client'
import { useEffect, useState } from 'react'
import { API_BASE } from '@/lib/config'
import { authHeaders } from '@/lib/api/auth'

export interface SessionMemory {
  created_at: string
  highlight:  string
}

export interface RecentSession {
  session_date:   string
  form_score:     number | null
  summary:        string | null
  exercises:      string[]
}

export interface RiskProfile {
  suggested_exercises?: string[]
  risky_exercises?:     string[]
  affected_body_parts?: { part: string; weight: number }[]
}

export interface PatientProfile {
  id:                  string
  name:                string
  date_of_birth:       string | null
  notes:               string | null
  doctor_note:         string | null
  risk_profile:        RiskProfile
  assigned_exercises:  string[]
  session_memories:    SessionMemory[]
  recent_sessions:     RecentSession[]
}

// Fetches GET /patients/{id} — same shape the backend returns from
// patients.py::_patient_with_sessions. Demo endpoint is unauthenticated,
// like /gym.
export function usePatientProfile(patientId: string | null) {
  const [profile, setProfile] = useState<PatientProfile | null>(null)
  const [error, setError]     = useState<string | null>(null)

  useEffect(() => {
    setProfile(null)
    setError(null)
    if (!patientId) return

    let cancelled = false
    ;(async () => {
      try {
        const res = await fetch(`${API_BASE}/patients/${patientId}`, {
          headers: authHeaders(),
        })
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data = (await res.json()) as PatientProfile
        if (!cancelled) setProfile(data)
      } catch (exc) {
        if (!cancelled) setError((exc as Error).message)
      }
    })()
    return () => { cancelled = true }
  }, [patientId])

  return { profile, error }
}
