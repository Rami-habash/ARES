'use client'
import { useRouter, useSearchParams } from 'next/navigation'
import { useEffect, useState } from 'react'
import { API_BASE } from '@/lib/config'
import { authHeaders } from '@/lib/api/auth'
import { useGymSession } from '@/hooks/useGymSession'
import PatientGuard from '@/components/patient/PatientGuard'
import PatientHeader from '@/components/patient/PatientHeader'

function LostContent() {
  const router = useRouter()
  const params = useSearchParams()
  const sessionId = Number(params.get('session_id'))
  const validId = Number.isFinite(sessionId) && sessionId > 0 ? sessionId : null
  const { session } = useGymSession(validId)
  const [busy, setBusy] = useState<'stay' | 'leave' | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!session || !validId) return
    if (session.state === 'ACTIVE')      router.replace(`/patient/marker?session_id=${validId}`)
    if (session.state === 'CHECKING_IN') router.replace(`/patient/marker?session_id=${validId}`)
    if (session.state === 'LEFT')        router.replace('/patient/check-in')
  }, [session, validId, router])

  const stillHere = async () => {
    if (!validId) return
    setBusy('stay')
    setError(null)
    try {
      const r = await fetch(`${API_BASE}/gym/${validId}/still_here`, {
        method: 'POST',
        headers: authHeaders(),
      })
      if (!r.ok) {
        const data = await r.json().catch(() => ({}))
        setError(data.detail ?? `HTTP ${r.status}`)
        setBusy(null)
        return
      }
      router.replace(`/patient/marker?session_id=${validId}`)
    } catch (exc) {
      setError((exc as Error).message)
      setBusy(null)
    }
  }

  const leave = async () => {
    if (!validId) return
    setBusy('leave')
    try {
      await fetch(`${API_BASE}/gym/${validId}/leave`, { method: 'POST', headers: authHeaders() })
    } finally {
      router.replace('/patient/check-in')
    }
  }

  if (!validId) {
    return (
      <div className="flex flex-col flex-1 justify-center text-center gap-4">
        <p className="text-red-600">Missing session_id.</p>
        <button onClick={() => router.replace('/patient/check-in')} className="underline text-[#1a1208]/60">
          Start over
        </button>
      </div>
    )
  }

  return (
    <div className="flex flex-col flex-1">
      <PatientHeader />

      <div className="flex flex-col flex-1 justify-center text-center gap-6">
        <div>
          <p className="text-sm uppercase tracking-widest text-[#c45c1a] font-semibold">
            We lost track of you
          </p>
          <h1 className="text-2xl font-bold mt-2 text-[#1a1208] text-balance">
            Are you still in the gym?
          </h1>
        </div>

        <button
          onClick={stillHere}
          disabled={busy !== null}
          className="rounded-xl bg-[#e8622c] hover:bg-[#d4561f] disabled:opacity-50 text-white text-lg font-semibold py-4 transition-colors"
        >
          {busy === 'stay' ? 'Showing marker…' : "I'm still here"}
        </button>

        <button
          onClick={leave}
          disabled={busy !== null}
          className="rounded-xl border border-[#1a1208]/15 hover:bg-[#1a1208]/5 disabled:opacity-50 text-[#1a1208]/60 text-base font-medium py-3 transition-colors"
        >
          {busy === 'leave' ? 'Leaving…' : "I'm leaving"}
        </button>

        {error && (
          <p className="text-sm text-red-600 break-words">{error}</p>
        )}
      </div>
    </div>
  )
}

export default function PatientLostPage() {
  return (
    <PatientGuard>
      {() => <LostContent />}
    </PatientGuard>
  )
}
