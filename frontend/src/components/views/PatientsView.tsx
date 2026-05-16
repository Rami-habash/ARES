'use client'
import SectionLabel from '@/components/shared/SectionLabel'
import StatusPill from '@/components/shared/StatusPill'
import { useSimulatedUpdates } from '@/hooks/useSimulatedUpdates'
import type { NavItem } from '@/types'

interface Props {
  setActiveView: (v: NavItem) => void
  setSelectedPatient: (id: string) => void
  demo: { liveUpdates: boolean }
}

export default function PatientsView({ setActiveView, setSelectedPatient, demo }: Props) {
  const patients = useSimulatedUpdates(demo.liveUpdates)

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <div className="mb-6">
        <SectionLabel>Patient Roster</SectionLabel>
        <h1 className="text-2xl font-bold text-text-primary">Active Patients</h1>
      </div>

      <div className="bg-card rounded-xl border border-border shadow-sm overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-slate-50">
              {['Patient', 'Status', 'Exercise', 'Form Score', 'Risk', 'Adherence', 'Confidence', ''].map(h => (
                <th key={h} className="text-left px-4 py-3 text-xs font-semibold uppercase tracking-wider text-text-muted">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {patients.map(p => (
              <tr key={p.id} className="border-b border-border/50 hover:bg-slate-50 transition-colors">
                <td className="px-4 py-3">
                  <div className="font-semibold text-text-primary">{p.name}</div>
                  <div className="text-xs text-text-muted">{p.id} · {p.zone}</div>
                </td>
                <td className="px-4 py-3"><StatusPill status={p.status} /></td>
                <td className="px-4 py-3 text-text-muted">{p.currentExercise}</td>
                <td className="px-4 py-3 font-mono font-bold text-text-primary">{Math.round(p.formScore)}</td>
                <td className="px-4 py-3">
                  <span className={`text-xs font-medium px-2 py-0.5 rounded ${
                    p.riskScore === 'High' ? 'bg-red-100 text-red-700' :
                    p.riskScore === 'Medium' ? 'bg-amber-100 text-amber-700' :
                    'bg-green-100 text-green-700'
                  }`}>{p.riskScore}</span>
                </td>
                <td className="px-4 py-3 text-text-muted">{p.adherence}%</td>
                <td className="px-4 py-3 text-text-muted">{Math.round(p.trackingConfidence)}%</td>
                <td className="px-4 py-3">
                  <button
                    onClick={() => { setSelectedPatient(p.id); setActiveView('exercise') }}
                    className="text-xs text-accent-blue hover:underline font-medium"
                  >
                    View →
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
