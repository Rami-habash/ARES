'use client'
import StatusPill from '@/components/shared/StatusPill'
import EventTimeline from '@/components/dashboard/EventTimeline'
import type { Patient } from '@/types'

interface Props { patient: Patient | null }

export default function PatientInspector({ patient }: Props) {
  if (!patient) {
    return (
      <div className="flex items-center justify-center h-full text-text-muted text-sm">
        Click a patient to inspect
      </div>
    )
  }

  return (
    <div className="p-4 space-y-4 overflow-auto h-full">
      <div>
        <div className="flex items-center gap-2 mb-1">
          <h3 className="font-bold text-text-primary">{patient.name}</h3>
          <StatusPill status={patient.status} />
        </div>
        <p className="text-xs text-text-muted">{patient.id} · {patient.zone} · Age {patient.age}</p>
      </div>

      <div className="grid grid-cols-2 gap-2">
        {[
          { label: 'Form Score', value: `${Math.round(patient.formScore)}/100` },
          { label: 'Confidence', value: `${Math.round(patient.trackingConfidence)}%` },
          { label: 'Adherence', value: `${patient.adherence}%` },
          { label: 'Risk', value: patient.riskScore },
        ].map(item => (
          <div key={item.label} className="bg-slate-50 rounded-lg p-2">
            <p className="text-xs text-text-muted">{item.label}</p>
            <p className="font-semibold text-sm text-text-primary">{item.value}</p>
          </div>
        ))}
      </div>

      <div>
        <p className="text-xs font-semibold uppercase tracking-widest text-text-muted mb-2">Current Exercise</p>
        <p className="text-sm font-medium text-text-primary">{patient.currentExercise}</p>
      </div>

      {patient.restrictions.length > 0 && (
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest text-text-muted mb-2">Restrictions</p>
          <ul className="space-y-1">
            {patient.restrictions.map(r => (
              <li key={r} className="text-xs text-accent-red bg-red-50 px-2 py-1 rounded">{r}</li>
            ))}
          </ul>
        </div>
      )}

      <div>
        <p className="text-xs font-semibold uppercase tracking-widest text-text-muted mb-2">Recent Events</p>
        <EventTimeline events={patient.recentEvents} />
      </div>
    </div>
  )
}
