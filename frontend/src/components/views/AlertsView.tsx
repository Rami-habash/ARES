'use client'
import { useState } from 'react'
import SectionLabel from '@/components/shared/SectionLabel'
import AlertCard from '@/components/alerts/AlertCard'
import TriageSummary from '@/components/alerts/TriageSummary'
import { MOCK_ALERTS } from '@/data/alerts'
import type { Alert, AlertSeverity } from '@/types'

type Tab = 'All' | AlertSeverity

export default function AlertsView() {
  const [alerts, setAlerts] = useState<Alert[]>(MOCK_ALERTS)
  const [tab, setTab] = useState<Tab>('All')

  const dismiss = (id: string) => setAlerts(prev => prev.map(a => a.id === id ? { ...a, status: 'Dismissed' as const } : a))
  const escalate = (id: string) => setAlerts(prev => prev.map(a => a.id === id ? { ...a, status: 'Escalated' as const } : a))

  const visible = alerts.filter(a => tab === 'All' || a.severity === tab)

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <div className="mb-6">
        <SectionLabel>Alert Queue</SectionLabel>
        <h1 className="text-2xl font-bold text-text-primary">Active Alerts</h1>
      </div>

      <div className="grid grid-cols-3 gap-6">
        <div className="col-span-2">
          <div className="flex gap-2 mb-4">
            {(['All', 'Critical', 'Warning', 'Info'] as Tab[]).map(t => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                  tab === t ? 'bg-sidebar text-white' : 'bg-slate-100 text-text-muted hover:bg-slate-200'
                }`}
              >
                {t}
              </button>
            ))}
          </div>
          <div className="space-y-3">
            {visible.map(alert => (
              <AlertCard key={alert.id} alert={alert} onDismiss={dismiss} onEscalate={escalate} />
            ))}
            {visible.length === 0 && (
              <div className="text-center py-12 text-text-muted">No alerts in this category</div>
            )}
          </div>
        </div>
        <TriageSummary alerts={alerts} />
      </div>
    </div>
  )
}
