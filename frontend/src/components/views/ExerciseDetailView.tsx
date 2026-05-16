'use client'
import { useEffect, useState } from 'react'
import SectionLabel from '@/components/shared/SectionLabel'
import CoachingPanel from '@/components/exercise/CoachingPanel'
import LiveCameraCanvas from '@/components/room-monitor/LiveCameraCanvas'
import { useLiveStream } from '@/components/providers/LiveStreamProvider'
import { useGymSessions, type GymSession } from '@/hooks/useGymSessions'
import { usePatientProfile, type PatientProfile } from '@/hooks/usePatientProfile'
import { endSessionAndReport, leaveSession, stillHere } from '@/lib/api/gym'

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
        {sessions.map((s) => (
          <PatientCard key={s.id} session={s} onClick={() => setSelectedId(s.patient_id)} />
        ))}
      </div>
    </div>
  )
}

// ── Card on the patient list (uses the profile so the real name shows up) ───

function PatientCard({ session, onClick }: { session: GymSession; onClick: () => void }) {
  const tag = stateLabel[session.state]
  const { profile } = usePatientProfile(session.patient_id)

  return (
    <button
      onClick={onClick}
      className="text-left rounded-xl border border-border bg-card p-5 hover:border-accent-blue hover:shadow-sm transition"
    >
      <div className="flex items-center justify-between mb-2">
        <div className="min-w-0">
          <p className="font-semibold text-text-primary truncate">
            {profile?.name ?? session.patient_id}
          </p>
          <p className="font-mono text-xs text-text-muted">{session.patient_id}</p>
        </div>
        <span className={`text-[10px] font-semibold px-2 py-0.5 rounded border ${tag.classes}`}>
          {tag.text}
        </span>
      </div>
      <p className="text-xs text-text-muted">
        session #{session.id} · since {new Date(session.started_at + 'Z').toLocaleTimeString()}
      </p>
      {profile && profile.assigned_exercises.length > 0 && (
        <p className="text-xs text-text-muted mt-2 truncate">
          {profile.assigned_exercises.join(' · ')}
        </p>
      )}
    </button>
  )
}

// ── The active coaching workspace for one patient ──────────────────────────

function PatientCoachingView({ session, onBack }: { session: GymSession; onBack: () => void }) {
  const tag = stateLabel[session.state]
  const { detail } = useLiveStream()
  const { profile, error: profileError } = usePatientProfile(session.patient_id)
  const broadcasting = detail.status === 'broadcasting'

  const [report, setReport]     = useState<string | null>(null)
  const [busy, setBusy]         = useState<'leave' | 'still_here' | 'report' | null>(null)
  const [actionError, setError] = useState<string | null>(null)

  const handleLeave = async () => {
    if (busy) return
    setBusy('leave')
    setError(null)
    try {
      await leaveSession(session.id)
      onBack()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  const handleStillHere = async () => {
    if (busy) return
    setBusy('still_here')
    setError(null)
    try {
      await stillHere(session.id)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  const handleReport = async () => {
    if (busy) return
    setBusy('report')
    setError(null)
    try {
      const data = await endSessionAndReport(session.id)
      setReport(data.report)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  const displayName = profile?.name ?? session.patient_id

  return (
    <div className="flex flex-col h-full p-6 gap-4">
      {report && (
        <ReportModal
          patientId={session.patient_id}
          report={report}
          onClose={() => { setReport(null); onBack() }}
        />
      )}

      <div>
        <button
          onClick={onBack}
          className="text-sm text-text-muted hover:text-text-primary mb-2"
        >
          ← Back to patients
        </button>
        <SectionLabel>Exercise Detail</SectionLabel>
        <div className="flex items-center gap-3 mt-1 flex-wrap">
          <h1 className="text-2xl font-bold text-text-primary">{displayName}</h1>
          <span className="font-mono text-sm text-text-muted">{session.patient_id}</span>
          <span className={`text-xs font-semibold px-2 py-0.5 rounded border ${tag.classes}`}>
            {tag.text}
          </span>
        </div>
        <p className="text-text-muted mt-1">
          session #{session.id} · since {new Date(session.started_at + 'Z').toLocaleTimeString()}
        </p>
        {profileError && (
          <p className="text-xs text-accent-red mt-1">
            Could not load profile: {profileError}
          </p>
        )}
      </div>

      <SessionControls
        state={session.state}
        busy={busy}
        onLeave={handleLeave}
        onStillHere={handleStillHere}
        onReport={handleReport}
        error={actionError}
      />

      <div className="flex gap-4 flex-1 min-h-0">
        <div className="flex-1 min-w-0 relative">
          <LiveCameraCanvas
            latestFrame={detail.latestFrame}
            sourceSize={detail.sourceSize}
            selectedPatientId={session.patient_id}
            filterPatientId={session.patient_id}
            showKeypoints
            mjpegSrc={`${process.env.NEXT_PUBLIC_CV_LOCAL ?? 'http://localhost:8001'}/live/mjpeg?stream=detail`}
          />
          {!broadcasting && (
            <div className="absolute inset-0 flex items-center justify-center bg-black/60 rounded-lg">
              <div className="text-center px-6">
                <p className="text-white/80 text-sm mb-3">
                  Share this laptop&apos;s webcam for high-fidelity pose analysis.
                </p>
                <button
                  onClick={detail.start}
                  className="rounded-md bg-accent-blue hover:opacity-90 text-white text-sm font-medium px-4 py-2"
                >
                  {detail.status === 'requesting-camera' ? 'Requesting camera…' :
                   detail.status === 'connecting' ? 'Connecting…' : 'Start detail camera'}
                </button>
              </div>
            </div>
          )}
        </div>

        <div className="w-80 flex-shrink-0 overflow-auto flex flex-col gap-4">
          <CoachingPanel patientId={session.patient_id} patientName={displayName} />
          <PatientContextPanel profile={profile} />
        </div>
      </div>
    </div>
  )
}

// ── Session control bar (Leave / Still here / End session + report) ────────

function SessionControls({
  state, busy, onLeave, onStillHere, onReport, error,
}: {
  state:       GymSession['state']
  busy:        'leave' | 'still_here' | 'report' | null
  onLeave:     () => void
  onStillHere: () => void
  onReport:    () => void
  error:       string | null
}) {
  const reportable = state === 'ACTIVE' || state === 'LOST'

  return (
    <div className="rounded-xl border border-border bg-card p-3 flex items-center gap-2 flex-wrap">
      {state === 'LOST' && (
        <button
          onClick={onStillHere}
          disabled={busy !== null}
          className="rounded-md bg-accent-blue hover:opacity-90 disabled:opacity-50 text-white text-sm font-medium px-3 py-1.5"
        >
          {busy === 'still_here' ? 'Re-arming marker…' : 'I’m still here'}
        </button>
      )}
      {reportable && (
        <button
          onClick={onReport}
          disabled={busy !== null}
          className="rounded-md bg-slate-700 hover:bg-slate-900 disabled:opacity-50 text-white text-sm font-medium px-3 py-1.5"
        >
          {busy === 'report' ? 'Generating report…' : 'End session + report'}
        </button>
      )}
      <button
        onClick={onLeave}
        disabled={busy !== null || state === 'LEFT'}
        className="rounded-md border border-border text-text-primary hover:bg-slate-50 disabled:opacity-50 text-sm font-medium px-3 py-1.5"
      >
        {busy === 'leave' ? 'Leaving…' : 'Leave (no report)'}
      </button>
      {error && (
        <span className="text-xs text-accent-red ml-2">{error}</span>
      )}
    </div>
  )
}

// ── Patient context (assigned exercises + recent session memories) ─────────

function PatientContextPanel({ profile }: { profile: PatientProfile | null }) {
  if (!profile) {
    return (
      <div className="bg-card rounded-xl border border-border p-5 shadow-sm">
        <p className="text-xs font-semibold uppercase tracking-widest text-text-muted mb-1">
          Patient context
        </p>
        <p className="text-sm text-text-muted italic">Loading profile…</p>
      </div>
    )
  }

  const memories = profile.session_memories.slice(0, 5)
  const risky    = profile.risk_profile?.risky_exercises ?? []

  return (
    <div className="bg-card rounded-xl border border-border p-5 shadow-sm flex flex-col gap-4">
      <div>
        <p className="text-xs font-semibold uppercase tracking-widest text-text-muted mb-1">
          Assigned exercises
        </p>
        {profile.assigned_exercises.length === 0 ? (
          <p className="text-sm text-text-muted italic">None assigned</p>
        ) : (
          <ul className="text-sm text-text-primary list-disc pl-5 space-y-0.5">
            {profile.assigned_exercises.map(ex => (
              <li key={ex}>{ex}</li>
            ))}
          </ul>
        )}
      </div>

      {risky.length > 0 && (
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest text-text-muted mb-1">
            Risky for this patient
          </p>
          <p className="text-sm text-accent-red">{risky.join(', ')}</p>
        </div>
      )}

      {profile.notes && (
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest text-text-muted mb-1">
            Notes
          </p>
          <p className="text-sm text-text-primary leading-snug">{profile.notes}</p>
        </div>
      )}

      <div>
        <p className="text-xs font-semibold uppercase tracking-widest text-text-muted mb-1">
          Recent session memories
        </p>
        {memories.length === 0 ? (
          <p className="text-sm text-text-muted italic">No prior memories</p>
        ) : (
          <ul className="space-y-2">
            {memories.map((m, i) => (
              <li key={`${m.created_at}-${i}`} className="text-xs">
                <p className="text-text-muted">{m.created_at}</p>
                <p className="text-text-primary leading-snug">{m.highlight}</p>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

// ── Report modal ───────────────────────────────────────────────────────────

function ReportModal({
  patientId, report, onClose,
}: { patientId: string; report: string; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-2xl max-h-[80vh] flex flex-col mx-4">
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <h2 className="font-semibold text-text-primary">Session Report — {patientId}</h2>
          <button onClick={onClose} className="text-text-muted hover:text-text-primary text-xl leading-none">✕</button>
        </div>
        <div className="flex-1 overflow-auto px-6 py-4">
          <pre className="whitespace-pre-wrap text-sm text-text-primary font-mono leading-relaxed">{report}</pre>
        </div>
        <div className="px-6 py-4 border-t border-border">
          <button onClick={onClose}
            className="rounded-md bg-slate-800 hover:bg-slate-900 text-white text-sm font-medium px-4 py-2">
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
