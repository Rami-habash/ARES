'use client'
import { useState } from 'react'
import EventTimeline from '@/components/dashboard/EventTimeline'
import { MOCK_PATIENTS } from '@/data/patients'

interface Props { patientId: string | null }

export default function ReportPreview({ patientId }: Props) {
  const patient = MOCK_PATIENTS.find(p => p.id === patientId) ?? MOCK_PATIENTS[0]
  const [reviewed, setReviewed] = useState(false)

  return (
    <div className="bg-card rounded-xl border border-border shadow-sm p-8 max-w-3xl mx-auto">
      <div className="border-b border-border pb-6 mb-6">
        <p className="text-xs text-text-muted uppercase tracking-widest mb-1">Movement Monitoring Report</p>
        <h2 className="text-2xl font-bold text-text-primary">{patient.name}</h2>
        <p className="text-text-muted mt-1">{patient.id} · Session: {new Date().toLocaleDateString()} · Clinician: Dr. A. Martinez (placeholder)</p>
      </div>

      {[
        {
          title: 'Summary',
          content: `Patient completed ${patient.currentExercise} with a form score of ${Math.round(patient.formScore)}/100. Overall adherence to rehab plan: ${patient.adherence}%. Risk classification: ${patient.riskScore}.`,
        },
        {
          title: 'Exercises Performed',
          content: patient.assignedExercises.join(' · '),
        },
        {
          title: 'Form Findings',
          content: 'Right knee valgus detected during squat descent (8.2° vs <5° reference). Trunk forward lean noted at 13.5°. Descent speed marginally fast at 1.8s vs 2-3s reference.',
        },
        {
          title: 'Safety Events',
          content: patient.status === 'At Risk'
            ? 'CRITICAL: Lateral sway exceeded 15° threshold. Gait asymmetry detected. PT intervention recommended.'
            : 'No safety-critical events during session.',
        },
        {
          title: 'AI Summary',
          content: 'AI coaching system identified right knee valgus as primary correction target. Recommended cuing hip external rotation and ankle mobility intervention.',
        },
      ].map(section => (
        <div key={section.title} className="mb-6">
          <p className="text-xs font-semibold uppercase tracking-widest text-text-muted mb-2">{section.title}</p>
          <p className="text-sm text-text-primary leading-relaxed">{section.content}</p>
        </div>
      ))}

      <div className="mb-6">
        <p className="text-xs font-semibold uppercase tracking-widest text-text-muted mb-2">Session Timeline</p>
        <EventTimeline events={patient.recentEvents} />
      </div>

      <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 mb-6">
        <p className="text-xs text-amber-700">
          <strong>Demo note:</strong> This report is a movement-monitoring summary and does not replace clinical judgment.
        </p>
      </div>

      <div className="flex gap-3">
        <button
          onClick={() => window.print()}
          className="px-4 py-2 bg-sidebar text-white rounded-lg text-sm font-medium hover:opacity-90 transition-opacity"
        >
          Download PDF
        </button>
        <button
          onClick={() => navigator.clipboard.writeText(patient.name + ' session report')}
          className="px-4 py-2 bg-slate-100 text-text-primary rounded-lg text-sm font-medium hover:bg-slate-200 transition-colors"
        >
          Copy Summary
        </button>
        <button
          onClick={() => setReviewed(true)}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${reviewed ? 'bg-green-100 text-green-700' : 'bg-slate-100 text-text-muted hover:bg-slate-200'}`}
        >
          {reviewed ? '✓ Reviewed' : 'Mark Reviewed'}
        </button>
      </div>
    </div>
  )
}
