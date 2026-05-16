'use client'
import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import { API_BASE } from '@/lib/config'
import { DEMO_PATIENT_ID } from '@/lib/patient'
import type { GymSession } from '@/hooks/useGymSessions'

// Step 1 of the patient flow. If the patient already has an active session
// (CHECKING_IN / ACTIVE / LOST), we route them straight to the matching screen
// instead of trying to create a new one and 409-ing.
export default function PatientCheckInPage() {
  const router = useRouter()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // If there's already an active session in the DB, jump to the right screen.
  // /gym/check_in is idempotent now, so this is purely a UX shortcut — the
  // patient doesn't have to tap Check in again after a page reload.
  useEffect(() => {
    let stopped = false
    const find = async () => {
      try {
        const r = await fetch(`${API_BASE}/gym`)
        if (!r.ok) return
        const data: GymSession[] = await r.json()
        const mine = data.find((s) => s.patient_id === DEMO_PATIENT_ID)
        if (stopped || !mine) return
        if (mine.state === 'LOST') router.replace(`/patient/lost?session_id=${mine.id}`)
        else router.replace(`/patient/marker?session_id=${mine.id}`)
      } catch {
        /* ignore — they can still tap check in */
      }
    }
    find()
    return () => { stopped = true }
  }, [router])

  const checkIn = async () => {
    setBusy(true)
    setError(null)
    try {
      const r = await fetch(`${API_BASE}/gym/check_in`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ patient_id: DEMO_PATIENT_ID }),
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
    <div className="flex flex-col flex-1 justify-center text-center gap-6">
      <div>
        <p className="text-sm uppercase tracking-widest text-slate-400">Patient</p>
        <h1 className="text-3xl font-bold mt-1">{DEMO_PATIENT_ID}</h1>
      </div>

      <p className="text-slate-300 text-balance">
        Tap below to check in. We&apos;ll show you a marker — hold your phone screen up to the gym camera for a couple seconds and we&apos;ll find you.
      </p>

      <button
        onClick={checkIn}
        disabled={busy}
        className="rounded-xl bg-blue-500 hover:bg-blue-600 disabled:opacity-50 text-white text-lg font-semibold py-4"
      >
        {busy ? 'Checking in…' : 'Check in'}
      </button>

      {error && (
        <p className="text-sm text-red-400 break-words">{error}</p>
      )}
    </div>
  )
}
