'use client'
import { Dumbbell, ChevronRight } from 'lucide-react'
import StatusPill from '@/components/shared/StatusPill'
import type { Patient, NavItem } from '@/types'

interface Props {
  patient: Patient
  setActiveView: (v: NavItem) => void
  setSelectedPatient: (id: string) => void
}

const riskColors: Record<string, string> = {
  Low: 'bg-green-100 text-green-700',
  Medium: 'bg-amber-100 text-amber-700',
  High: 'bg-red-100 text-red-700',
}

export default function PatientCard({ patient, setActiveView, setSelectedPatient }: Props) {
  return (
    <div className="bg-card rounded-xl border border-border p-4 shadow-sm hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="font-semibold text-text-primary">{patient.name}</h3>
            <span className="text-xs text-text-muted bg-slate-100 px-1.5 py-0.5 rounded">{patient.id}</span>
          </div>
          <p className="text-xs text-text-muted mt-0.5">{patient.zone} · Age {patient.age}</p>
        </div>
        <StatusPill status={patient.status} />
      </div>

      <div className="flex items-center gap-1.5 text-sm text-text-muted mb-3">
        <Dumbbell className="w-3.5 h-3.5" />
        <span>{patient.currentExercise}</span>
      </div>

      <div className="mb-3">
        <div className="flex justify-between text-xs text-text-muted mb-1">
          <span>Tracking confidence</span>
          <span>{Math.round(patient.trackingConfidence)}%</span>
        </div>
        <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
          <div
            className="h-full bg-accent-blue rounded-full transition-all duration-700"
            style={{ width: `${patient.trackingConfidence}%` }}
          />
        </div>
      </div>

      <div className="flex items-center justify-between">
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${riskColors[patient.riskScore]}`}>
          {patient.riskScore} risk
        </span>
        <button
          onClick={() => { setSelectedPatient(patient.id); setActiveView('exercise') }}
          className="flex items-center gap-1 text-xs text-accent-blue hover:text-blue-700 font-medium transition-colors"
        >
          Open Detail
          <ChevronRight className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  )
}
