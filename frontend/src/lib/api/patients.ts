import { USE_MOCK } from '@/lib/config'
import { MOCK_PATIENTS } from '@/data/patients'
import type { Patient } from '@/types'

export async function getPatients(): Promise<Patient[]> {
  if (USE_MOCK) return MOCK_PATIENTS
  const res = await fetch(`${process.env.NEXT_PUBLIC_API_BASE}/patients`)
  return res.json()
}

export async function getPatient(id: string): Promise<Patient | undefined> {
  if (USE_MOCK) return MOCK_PATIENTS.find(p => p.id === id)
  const res = await fetch(`${process.env.NEXT_PUBLIC_API_BASE}/patients/${id}`)
  return res.json()
}
