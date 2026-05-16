'use client'
import { useState, useEffect, useCallback } from 'react'
import { MOCK_PATIENTS } from '@/data/patients'
import type { Patient } from '@/types'

export function useSimulatedUpdates(enabled: boolean) {
  const [patients, setPatients] = useState<Patient[]>(MOCK_PATIENTS)

  const tick = useCallback(() => {
    setPatients(prev => prev.map(p => ({
      ...p,
      trackingConfidence: Math.min(100, Math.max(50, p.trackingConfidence + (Math.random() * 4 - 2))),
      formScore: Math.min(100, Math.max(0, p.formScore + (Math.random() * 2 - 1))),
    })))
  }, [])

  useEffect(() => {
    if (!enabled) return
    const id = setInterval(tick, 3000)
    return () => clearInterval(id)
  }, [enabled, tick])

  return patients
}
