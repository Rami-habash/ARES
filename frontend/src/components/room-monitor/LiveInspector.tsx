'use client'
import { useState } from 'react'
import type { GymSession } from '@/hooks/useGymSessions'
import { API_BASE } from '@/lib/config'

interface Props {
  sessions:          GymSession[]
  sessionsError:     string | null
  selectedPatientId: string | null
  onSelectPatient:   (id: string | null) => void
}

const stateLabel: Record<GymSession['state'], { text: string; classes: string }> = {
  CHECKING_IN: { text: 'Checking in', classes: 'bg-amber-100 text-amber-800 border-amber-200' },
  ACTIVE:      { text: 'Active',      classes: 'bg-green-100 text-green-800 border-green-200' },
  LOST:        { text: 'Lost',        classes: 'bg-red-100 text-red-800 border-red-200' },
  LEFT:        { text: 'Left',        classes: 'bg-slate-100 text-slate-600 border-slate-200' },
}


function ReportModal({ patientId, report, onClose }: {
  patientId: string; report: string; onClose: () => void
}) {
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

export default function LiveInspector({
  sessions, sessionsError, selectedPatientId, onSelectPatient,
}: Props) {
  const [generating, setGenerating] = useState<number | null>(null)
  const [report, setReport] = useState<{ patientId: string; text: string } | null>(null)

  const handleEndSession = async (session: GymSession, e: React.MouseEvent) => {
    e.stopPropagation()
    setGenerating(session.id)
    try {
      const res = await fetch(`${API_BASE}/gym/${session.id}/report`, { method: 'POST' })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setReport({ patientId: data.patient_id, text: data.report })
    } catch (err) {
      alert(`Failed to generate report: ${(err as Error).message}`)
    } finally {
      setGenerating(null)
    }
  }

  return (
    <>
      {report && (
        <ReportModal
          patientId={report.patientId}
          report={report.text}
          onClose={() => setReport(null)}
        />
      )}

      <div className="h-full flex flex-col">
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
            const isGenerating = generating === s.id
            return (
              <button key={s.id} onClick={() => onSelectPatient(isSelected ? null : s.patient_id)}
                className={`w-full text-left rounded-md border px-3 py-2 transition ${
                  isSelected ? 'border-accent-blue bg-blue-50' : 'border-border hover:bg-slate-50'
                }`}>
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
                {(s.state === 'ACTIVE' || s.state === 'LOST') && (
                  <button
                    onClick={(e) => handleEndSession(s, e)}
                    disabled={isGenerating}
                    className="mt-2 w-full rounded bg-slate-700 hover:bg-slate-900 disabled:opacity-50 text-white text-xs font-medium px-2 py-1"
                  >
                    {isGenerating ? 'Generating report…' : 'End session + report'}
                  </button>
                )}
              </button>
            )
          })}
        </div>

      </div>
    </>
  )
}
