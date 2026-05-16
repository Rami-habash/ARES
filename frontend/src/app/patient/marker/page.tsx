'use client'
import { useRouter, useSearchParams } from 'next/navigation'
import { useEffect, useState } from 'react'
import { API_BASE } from '@/lib/config'
import { authHeaders } from '@/lib/api/auth'
import { useGymSession } from '@/hooks/useGymSession'
import PatientGuard from '@/components/patient/PatientGuard'
import PatientHeader from '@/components/patient/PatientHeader'

// Static pre-generated marker PNGs in public/markers/ (no CV server needed at runtime)
function markerUrl(patientId: string): string {
  const m = patientId.match(/\d+/)
  const id = m ? parseInt(m[0], 10) - 1 : 0
  return `/markers/marker_${id}.png`
}

function MarkerContent({ patientId }: { patientId: string }) {
  const router = useRouter()
  const params = useSearchParams()
  const sessionId = Number(params.get('session_id'))
  const validId = Number.isFinite(sessionId) && sessionId > 0 ? sessionId : null
  const { session, error } = useGymSession(validId)
  const [leaving, setLeaving] = useState(false)

  // Re-arm CV's marker watch on mount. Idempotent — safe to call on every page load.
  useEffect(() => {
    fetch(`${API_BASE}/gym/check_in`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ patient_id: patientId }),
    }).catch(() => {})
  }, [patientId])

  useEffect(() => {
    if (!session) return
    if (session.state === 'LOST') router.replace(`/patient/lost?session_id=${session.id}`)
    if (session.state === 'LEFT') router.replace('/patient/check-in')
  }, [session, router])

  const leave = async () => {
    if (!validId) return
    setLeaving(true)
    try {
      await fetch(`${API_BASE}/gym/${validId}/leave`, { method: 'POST', headers: authHeaders() })
    } finally {
      router.replace('/patient/check-in')
    }
  }

  const requestReport = () => {
    router.push(`/patient/report?session_id=${validId}`)
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

  const isActive = session?.state === 'ACTIVE'
  const banner =
    !session ? 'Loading…' :
    isActive ? 'Checked in — you can put your phone away' :
    session.state === 'CHECKING_IN' ? 'Hold this screen up to the gym camera' :
    'Loading…'
  const bannerColor = isActive
    ? 'bg-[#2d7a4f]/15 text-[#2d7a4f]'
    : 'bg-[#c45c1a]/10 text-[#c45c1a]'

  return (
    <div className="flex flex-col flex-1">
      <PatientHeader />

      <div className="flex flex-col flex-1 gap-4">
        <div className={`rounded-lg px-4 py-3 text-center text-sm font-medium ${bannerColor}`}>
          {banner}
        </div>

        <div className="flex-1 flex items-center justify-center bg-white rounded-2xl overflow-hidden shadow-sm">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={markerUrl(patientId)}
            alt="check-in marker"
            className="w-full h-full object-contain"
          />
        </div>

        {isActive && (
          <button
            onClick={requestReport}
            className="rounded-xl bg-[#e8622c] hover:bg-[#d4561f] text-white text-base font-semibold py-3.5 transition-colors"
          >
            Request my report
          </button>
        )}

        <button
          onClick={leave}
          disabled={leaving}
          className="rounded-xl border border-[#1a1208]/15 hover:bg-[#1a1208]/5 disabled:opacity-50 text-[#1a1208]/60 text-sm font-medium py-3 transition-colors"
        >
          {leaving ? 'Leaving…' : 'Leave gym'}
        </button>

        {error && (
          <p className="text-sm text-red-600 break-words">{error}</p>
        )}
      </div>
    </div>
  )
}

export default function PatientMarkerPage() {
  return (
    <PatientGuard>
      {(patientId) => <MarkerContent patientId={patientId} />}
    </PatientGuard>
  )
}
