'use client'
import SectionLabel from '@/components/shared/SectionLabel'
import StatusPill from '@/components/shared/StatusPill'
import PoseVideoMock from '@/components/exercise/PoseVideoMock'
import MovementDiffTable from '@/components/exercise/MovementDiffTable'
import CoachingPanel from '@/components/exercise/CoachingPanel'
import { MAYA_SQUAT_METRICS } from '@/data/exercises'
import { MOCK_PATIENTS } from '@/data/patients'

interface Props {
  selectedPatient: string | null
}

export default function ExerciseDetailView({ selectedPatient }: Props) {
  const patient = MOCK_PATIENTS.find(p => p.id === selectedPatient) ?? MOCK_PATIENTS[0]

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <div className="mb-6">
        <SectionLabel>Exercise Detail</SectionLabel>
        <div className="flex items-center gap-3 mt-1">
          <h1 className="text-2xl font-bold text-text-primary">{patient.currentExercise}</h1>
          <StatusPill status={patient.status} />
        </div>
        <p className="text-text-muted mt-1">{patient.name} · {patient.id} · {patient.zone} · Session in progress</p>
      </div>

      <div className="grid grid-cols-3 gap-6 mb-6">
        <div className="col-span-2">
          <PoseVideoMock />
        </div>
        <CoachingPanel patientName={patient.name.split(' ')[0]} />
      </div>

      <div>
        <SectionLabel>Movement Analysis</SectionLabel>
        <div className="mt-1">
          <MovementDiffTable metrics={MAYA_SQUAT_METRICS} />
        </div>
      </div>
    </div>
  )
}
