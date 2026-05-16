'use client'
import type { GymSession } from '@/hooks/useGymSessions'
import type { BroadcastStatus } from '@/hooks/useLiveSecurityStream'
import type { CoachingMessage } from '@/hooks/useCoachingFeed'

interface Props {
  broadcastStatus: BroadcastStatus
  onStartBroadcast: () => void
  onStopBroadcast:  () => void

  sessions:          GymSession[]
  sessionsError:     string | null
  selectedPatientId: string | null
  onSelectPatient:   (id: string | null) => void

  coachingMessages:  CoachingMessage[]
}

const stateLabel: Record<GymSession['state'], { text: string; classes: string }> = {
  CHECKING_IN: { text: 'Checking in', classes: 'bg-amber-100 text-amber-800 border-amber-200' },
  ACTIVE:      { text: 'Active',      classes: 'bg-green-100 text-green-800 border-green-200' },
  LOST:        { text: 'Lost',        classes: 'bg-red-100 text-red-800 border-red-200' },
  LEFT:        { text: 'Left',        classes: 'bg-slate-100 text-slate-600 border-slate-200' },
}

function BroadcastButton({ status, onStart, onStop }: { status: BroadcastStatus; onStart: () => void; onStop: () => void }) {
  if (status === 'broadcasting') {
    return (
      <button onClick={onStop} className="w-full rounded-md bg-slate-800 hover:bg-slate-900 text-white text-sm font-medium px-3 py-2">
        Stop broadcast
      </button>
    )
  }
  const label =
    status === 'requesting-camera' ? 'Requesting camera…' :
    status === 'connecting'        ? 'Connecting…' :
    'Start broadcast'
  const disabled = status === 'requesting-camera' || status === 'connecting'
  return (
    <button
      onClick={onStart}
      disabled={disabled}
      className="w-full rounded-md bg-accent-blue hover:opacity-90 disabled:opacity-50 text-white text-sm font-medium px-3 py-2"
    >
      {label}
    </button>
  )
}

export default function LiveInspector({
  broadcastStatus, onStartBroadcast, onStopBroadcast,
  sessions, sessionsError, selectedPatientId, onSelectPatient,
  coachingMessages,
}: Props) {
  const errorMsg = typeof broadcastStatus === 'object' ? broadcastStatus.error : null

  return (
    <div className="h-full flex flex-col">
      <div className="px-4 py-3 border-b border-border">
        <p className="text-xs font-semibold uppercase tracking-widest text-text-muted">Camera</p>
        <div className="mt-2">
          <BroadcastButton status={broadcastStatus} onStart={onStartBroadcast} onStop={onStopBroadcast} />
        </div>
        {errorMsg && (
          <p className="mt-2 text-xs text-accent-red break-words">{errorMsg}</p>
        )}
        {broadcastStatus === 'idle' && (
          <p className="mt-2 text-xs text-text-muted">
            Click start to share this laptop&apos;s webcam as the room camera.
          </p>
        )}
      </div>

      <div className="px-4 py-3 border-b border-border">
        <p className="text-xs font-semibold uppercase tracking-widest text-text-muted">Patients in room</p>
      </div>

      <div className="flex-1 overflow-auto px-4 py-2 space-y-2">
        {sessionsError && (
          <p className="text-xs text-accent-red">Backend unreachable: {sessionsError}</p>
        )}
        {!sessionsError && sessions.length === 0 && (
          <p className="text-xs text-text-muted">
            No active gym sessions. Open <code className="px-1 bg-slate-100 rounded">/patient/check-in</code> on a phone to start one.
          </p>
        )}
        {sessions.map((s) => {
          const isSelected = s.patient_id === selectedPatientId
          const tag = stateLabel[s.state]
          return (
            <button
              key={s.id}
              onClick={() => onSelectPatient(isSelected ? null : s.patient_id)}
              className={`w-full text-left rounded-md border px-3 py-2 transition ${
                isSelected ? 'border-accent-blue bg-blue-50' : 'border-border hover:bg-slate-50'
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="font-mono text-sm font-semibold text-text-primary">{s.patient_id}</span>
                <span className={`text-[10px] font-semibold px-2 py-0.5 rounded border ${tag.classes}`}>
                  {tag.text}
                </span>
              </div>
              <p className="text-xs text-text-muted mt-1">
                session #{s.id} · since {new Date(s.started_at + 'Z').toLocaleTimeString()}
              </p>
              {s.state === 'LOST' && (
                <p className="text-xs text-accent-red mt-1">Waiting for marker to re-appear.</p>
              )}
            </button>
          )
        })}
      </div>

      <div className="border-t border-border">
        <div className="px-4 py-3 border-b border-border">
          <p className="text-xs font-semibold uppercase tracking-widest text-text-muted">Coaching</p>
        </div>
        <div className="max-h-48 overflow-auto px-4 py-2 space-y-2">
          {coachingMessages.length === 0 && (
            <p className="text-xs text-text-muted">No coaching yet.</p>
          )}
          {coachingMessages.map((m, i) => (
            <div key={i} className="text-xs">
              <span className="text-text-muted font-mono mr-2">{m.ts}</span>
              <span className="font-mono text-[10px] text-slate-400 mr-2">{m.patient_id}</span>
              <span className="text-text-primary">{m.text}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}