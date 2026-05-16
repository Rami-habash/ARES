'use client'
import { useEffect, useState } from 'react'
import SectionLabel from '@/components/shared/SectionLabel'
import CoachingPanel from '@/components/exercise/CoachingPanel'
import { useGymSessions, type GymSession } from '@/hooks/useGymSessions'

const stateLabel: Record<GymSession['state'], { text: string; classes: string }> = {
  CHECKING_IN: { text: 'Checking in', classes: 'bg-amber-100 text-amber-800 border-amber-200' },
  ACTIVE:      { text: 'Active',      classes: 'bg-green-100 text-green-800 border-green-200' },
  LOST:        { text: 'Lost',        classes: 'bg-red-100 text-red-800 border-red-200' },
  LEFT:        { text: 'Left',        classes: 'bg-slate-100 text-slate-600 border-slate-200' },
}

export default function ExerciseDetailView() {
  const { sessions, error } = useGymSessions()
  const [selectedId, setSelectedId] = useState<string | null>(null)

  // If the selected patient leaves the room, deselect them.
  useEffect(() => {
    if (selectedId && !sessions.some(s => s.patient_id === selectedId)) {
      setSelectedId(null)
    }
  }, [sessions, selectedId])

  const selected = sessions.find(s => s.patient_id === selectedId) ?? null

  if (selected) {
    return <PatientCoachingView session={selected} onBack={() => setSelectedId(null)} />
  }

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <div className="mb-6">
        <SectionLabel>Exercise Detail</SectionLabel>
        <h1 className="text-2xl font-bold text-text-primary mt-1">Active Patients</h1>
        <p className="text-text-muted mt-1">
          Select a checked-in patient to start live coaching.
        </p>
      </div>

      {error && (
        <p className="text-sm text-accent-red mb-4">Backend unreachable: {error}</p>
      )}

      {!error && sessions.length === 0 && (
        <div className="rounded-xl border border-border bg-card p-8 text-center">
          <p className="text-text-muted text-sm">
            No active patients. Patients must check in via{' '}
            <code className="px-1 bg-slate-100 rounded">/patient/check-in</code>{' '}
            and show the marker to the room camera.
          </p>
        </div>
      )}

      <div className="grid grid-cols-2 gap-4">
        {sessions.map((s) => {
          const tag = stateLabel[s.state]
          return (
            <button
              key={s.id}
              onClick={() => setSelectedId(s.patient_id)}
              className="text-left rounded-xl border border-border bg-card p-5 hover:border-accent-blue hover:shadow-sm transition"
            >
              <div className="flex items-center justify-between mb-2">
                <span className="font-mono text-lg font-semibold text-text-primary">{s.patient_id}</span>
                <span className={`text-[10px] font-semibold px-2 py-0.5 rounded border ${tag.classes}`}>
                  {tag.text}
                </span>
              </div>
              <p className="text-xs text-text-muted">
                session #{s.id} · since {new Date(s.started_at + 'Z').toLocaleTimeString()}
              </p>
            </button>
          )
        })}
      </div>
    </div>
  )
}

function PatientCoachingView({ session, onBack }: { session: GymSession; onBack: () => void }) {
  const tag = stateLabel[session.state]
  return (
    <div className="p-8 max-w-4xl mx-auto">
      <button
        onClick={onBack}
        className="text-sm text-text-muted hover:text-text-primary mb-4"
      >
        ← Back to patients
      </button>

      <div className="mb-6">
        <SectionLabel>Exercise Detail</SectionLabel>
        <div className="flex items-center gap-3 mt-1">
          <h1 className="text-2xl font-bold text-text-primary font-mono">{session.patient_id}</h1>
          <span className={`text-xs font-semibold px-2 py-0.5 rounded border ${tag.classes}`}>
            {tag.text}
          </span>
        </div>
        <p className="text-text-muted mt-1">
          session #{session.id} · since {new Date(session.started_at + 'Z').toLocaleTimeString()}
        </p>
      </div>

      <CoachingPanel patientId={session.patient_id} patientName={session.patient_id} />
    </div>
  )
}
