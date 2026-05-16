'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { getToken, getPatientId, clearToken } from '@/lib/api/auth'

export interface PatientAuth {
  token: string | null
  patientId: string | null
  ready: boolean
  signOut: () => void
}

export function usePatientAuth(): PatientAuth {
  const [token, setToken] = useState<string | null>(null)
  const [patientId, setPatientId] = useState<string | null>(null)
  const [ready, setReady] = useState(false)
  const router = useRouter()

  useEffect(() => {
    setToken(getToken())
    setPatientId(getPatientId())
    setReady(true)
  }, [])

  const signOut = () => {
    clearToken()
    router.replace('/patient/sign-in')
  }

  return { token, patientId, ready, signOut }
}
