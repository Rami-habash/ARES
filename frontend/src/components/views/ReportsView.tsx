'use client'
import SectionLabel from '@/components/shared/SectionLabel'
import ReportPreview from '@/components/reports/ReportPreview'

interface Props { selectedPatient: string | null }

export default function ReportsView({ selectedPatient }: Props) {
  return (
    <div className="p-8 max-w-7xl mx-auto">
      <div className="mb-6">
        <SectionLabel>Session Reports</SectionLabel>
        <h1 className="text-2xl font-bold text-text-primary">Patient Report</h1>
      </div>
      <ReportPreview patientId={selectedPatient} />
    </div>
  )
}
