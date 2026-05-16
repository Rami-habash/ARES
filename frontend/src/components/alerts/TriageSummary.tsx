'use client'
import type { Alert } from '@/types'

interface Props { alerts: Alert[] }

export default function TriageSummary({ alerts }: Props) {
  const open = alerts.filter(a => a.status === 'Open')
  const critical = open.filter(a => a.severity === 'Critical')
  const warning = open.filter(a => a.severity === 'Warning')
  const info = open.filter(a => a.severity === 'Info')

  return (
    <div className="bg-card rounded-xl border border-border p-5 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-widest text-text-muted mb-4">Triage Summary</p>

      <div className="space-y-3 mb-6">
        {[
          { label: 'Critical', count: critical.length, color: 'text-accent-red' },
          { label: 'Warning', count: warning.length, color: 'text-accent-amber' },
          { label: 'Info', count: info.length, color: 'text-accent-blue' },
        ].map(item => (
          <div key={item.label} className="flex justify-between items-center">
            <span className="text-sm text-text-muted">{item.label}</span>
            <span className={`text-xl font-bold ${item.color}`}>{item.count}</span>
          </div>
        ))}
      </div>

      {critical.length > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3">
          <p className="text-xs font-bold text-red-700 mb-1">Recommended Action</p>
          <p className="text-xs text-red-600">Immediate PT intervention for {critical[0].patientName}</p>
        </div>
      )}
    </div>
  )
}
