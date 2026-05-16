'use client'
import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import { API_BASE } from '@/lib/config'
import { authHeaders } from '@/lib/api/auth'
import type { GymSession } from '@/hooks/useGymSessions'
import PatientGuard from '@/components/patient/PatientGuard'
import PatientHeader from '@/components/patient/PatientHeader'

function CheckInContent({ patientId, signOut }: { patientId: string; signOut: () => void }) {
  const router = useRouter()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // If the patient already has an active session, jump straight to the right screen.
  useEffect(() => {
    let stopped = false
    const find = async () => {
      try {
        const r = await fetch(`${API_BASE}/gym`, { headers: authHeaders() })
        if (!r.ok) return
        const data: GymSession[] = await r.json()
        const mine = data.find((s) => s.patient_id === patientId)
        if (stopped || !mine) return
        if (mine.state === 'LOST') router.replace(`/patient/lost?session_id=${mine.id}`)
        else router.replace(`/patient/marker?session_id=${mine.id}`)
      } catch {
        /* ignore — they can still tap check in */
      }
    }
    find()
    return () => { stopped = true }
  }, [router, patientId])

  const checkIn = async () => {
    setBusy(true)
    setError(null)
    try {
      const r = await fetch(`${API_BASE}/gym/check_in`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ patient_id: patientId }),
      })
      const data = await r.json()
      if (!r.ok) {
        setError(data.detail ?? `HTTP ${r.status}`)
        setBusy(false)
        return
      }
      router.push(`/patient/marker?session_id=${data.id}`)
    } catch (exc) {
      setError((exc as Error).message)
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-col flex-1">
      <PatientHeader />

      <div className="flex flex-col flex-1 justify-center text-center gap-6">
        <div>
          <h1 className="text-3xl font-bold text-[#1a1208]">Check In</h1>
          <p className="text-[#1a1208]/60 mt-2 text-balance">
            Tap below, then hold your phone screen up to the gym camera for a couple seconds.
          </p>
        </div>

        <button
          onClick={checkIn}
          disabled={busy}
          className="rounded-xl bg-[#e8622c] hover:bg-[#d4561f] disabled:opacity-50 text-white text-lg font-semibold py-4 transition-colors"
        >
          {busy ? 'Checking in…' : 'Check in'}
        </button>

        {error && (
          <p className="text-sm text-red-600 break-words">{error}</p>
        )}
      </div>

      <div className="text-center pt-6">
        <button
          onClick={signOut}
          className="text-xs text-[#1a1208]/40 hover:text-[#1a1208]/60 transition-colors"
        >
          Not you? Sign out
        </button>
      </div>
    </div>
  )
}

export default function PatientCheckInPage() {
  return (
    <PatientGuard>
      {(patientId, signOut) => <CheckInContent patientId={patientId} signOut={signOut} />}
    </PatientGuard>
  )
}
