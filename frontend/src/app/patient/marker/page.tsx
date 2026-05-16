'use client'
import { useRouter, useSearchParams } from 'next/navigation'
import { useEffect, useState } from 'react'
import { API_BASE, CV_BASE } from '@/lib/config'
import { DEMO_PATIENT_ID } from '@/lib/patient'
import { useGymSession } from '@/hooks/useGymSession'

const MARKER_URL = `${CV_BASE}/live/marker.png`

// Step 2: fullscreen marker. Polls /gym/{id} and:
//   - CHECKING_IN → "Hold your phone up to the camera"
//   - ACTIVE      → "Checked in ✓ — you can put your phone away"
//   - LOST        → bounce to /patient/lost
//   - LEFT        → bounce to /patient/check-in
export default function PatientMarkerPage() {
  const router = useRouter()
  const params = useSearchParams()
  const sessionId = Number(params.get('session_id'))
  const validId = Number.isFinite(sessionId) && sessionId > 0 ? sessionId : null
  const { session, error } = useGymSession(validId)
  const [leaving, setLeaving] = useState(false)

  // Re-arm CV's marker watch on mount. /gym/check_in is idempotent — if the
  // session is already ACTIVE the state stays ACTIVE; if CV was restarted
  // since check-in, this re-populates its in-memory registry.
  useEffect(() => {
    fetch(`${API_BASE}/gym/check_in`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ patient_id: DEMO_PATIENT_ID }),
    }).catch(() => {})
  }, [])

  useEffect(() => {
    if (!session) return
    if (session.state === 'LOST') router.replace(`/patient/lost?session_id=${session.id}`)
    if (session.state === 'LEFT') router.replace('/patient/check-in')
  }, [session, router])

  const leave = async () => {
    if (!validId) return
    setLeaving(true)
    try {
      await fetch(`${API_BASE}/gym/${validId}/leave`, { method: 'POST' })
    } finally {
      router.replace('/patient/check-in')
    }
  }

  if (!validId) {
    return (
      <div className="flex flex-col flex-1 justify-center text-center gap-4">
        <p className="text-red-400">Missing session_id.</p>
        <button onClick={() => router.replace('/patient/check-in')} className="underline">
          Start over
        </button>
      </div>
    )
  }

  const banner =
    !session ? 'Loading…' :
    session.state === 'ACTIVE'      ? 'Checked in ✓ — you can put your phone away' :
    session.state === 'CHECKING_IN' ? 'Hold this screen up to the gym camera' :
    'Loading…'
  const bannerColor =
    session?.state === 'ACTIVE' ? 'bg-green-500/20 text-green-300' :
    'bg-blue-500/20 text-blue-200'

  return (
    <div className="flex flex-col flex-1 gap-4">
      <div className={`rounded-lg px-4 py-3 text-center text-sm font-medium ${bannerColor}`}>
        {banner}
      </div>

      <div className="flex-1 flex items-center justify-center bg-white rounded-2xl overflow-hidden">
        {/* The marker PNG comes from CV. eslint-disable: it's a runtime URL, not a static asset. */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={MARKER_URL}
          alt="check-in marker"
          className="w-full h-full object-contain"
        />
      </div>

      <button
        onClick={leave}
        disabled={leaving}
        className="rounded-xl bg-slate-800 hover:bg-slate-700 disabled:opacity-50 text-white text-base font-medium py-3"
      >
        {leaving ? 'Leaving…' : 'Leave gym'}
      </button>

      {error && (
        <p className="text-sm text-red-400 break-words">{error}</p>
      )}
    </div>
  )
}
