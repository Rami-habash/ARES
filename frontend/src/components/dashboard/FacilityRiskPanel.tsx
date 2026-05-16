'use client'
import type { Patient } from '@/types'

interface Props { patients: Patient[] }

export default function FacilityRiskPanel({ patients }: Props) {
  const highRisk = patients.filter(p => p.riskScore === 'High')
  const medRisk = patients.filter(p => p.riskScore === 'Medium')
  const lowRisk = patients.filter(p => p.riskScore === 'Low')

  return (
    <div className="bg-card rounded-xl border border-border p-5 shadow-sm h-full">
      <p className="text-xs font-semibold uppercase tracking-widest text-text-muted mb-4">Facility Risk Overview</p>
      <div className="space-y-3">
        {[
          { label: 'High Risk', patients: highRisk, color: 'bg-red-500' },
          { label: 'Medium Risk', patients: medRisk, color: 'bg-amber-400' },
          { label: 'Low Risk', patients: lowRisk, color: 'bg-green-500' },
        ].map(tier => (
          <div key={tier.label}>
            <div className="flex justify-between text-xs mb-1">
              <span className="text-text-muted">{tier.label}</span>
              <span className="font-medium text-text-primary">{tier.patients.length}</span>
            </div>
            <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full ${tier.color} transition-all duration-700`}
                style={{ width: `${(tier.patients.length / patients.length) * 100}%` }}
              />
            </div>
            <div className="mt-1 flex flex-wrap gap-1">
              {tier.patients.map(p => (
                <span key={p.id} className="text-xs text-text-muted">{p.name.split(' ')[0]}</span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
