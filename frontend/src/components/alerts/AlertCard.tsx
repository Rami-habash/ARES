'use client'
import { X, ChevronUp, Play } from 'lucide-react'
import type { Alert } from '@/types'

interface Props {
  alert: Alert
  onDismiss: (id: string) => void
  onEscalate: (id: string) => void
}

const severityConfig = {
  Critical: { bar: 'bg-accent-red', badge: 'bg-red-100 text-red-700' },
  Warning: { bar: 'bg-accent-amber', badge: 'bg-amber-100 text-amber-700' },
  Info: { bar: 'bg-accent-blue', badge: 'bg-blue-100 text-blue-700' },
}

export default function AlertCard({ alert, onDismiss, onEscalate }: Props) {
  const config = severityConfig[alert.severity]

  return (
    <div className="bg-card rounded-xl border border-border shadow-sm overflow-hidden flex">
      <div className={`w-1 flex-shrink-0 ${config.bar}`} />
      <div className="flex-1 p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1">
              <span className={`text-xs font-bold px-2 py-0.5 rounded ${config.badge}`}>{alert.severity}</span>
              <span className="text-xs text-text-muted">{alert.timestamp}</span>
              {alert.status !== 'Open' && (
                <span className="text-xs bg-slate-100 text-slate-500 px-2 py-0.5 rounded capitalize">{alert.status}</span>
              )}
            </div>
            <h3 className="font-semibold text-text-primary">{alert.title}</h3>
            <p className="text-sm text-text-muted mt-0.5">{alert.patientName} · {alert.description}</p>
            <span className="inline-block mt-2 text-xs bg-slate-100 text-slate-600 px-2 py-0.5 rounded font-mono">{alert.metric}</span>
          </div>
          <div className="flex gap-2 flex-shrink-0">
            <button
              onClick={() => onDismiss(alert.id)}
              className="p-1.5 rounded-lg hover:bg-slate-100 text-text-muted hover:text-text-primary transition-colors"
              title="Dismiss"
            >
              <X className="w-4 h-4" />
            </button>
            <button
              onClick={() => onEscalate(alert.id)}
              className="p-1.5 rounded-lg hover:bg-red-50 text-text-muted hover:text-accent-red transition-colors"
              title="Escalate"
            >
              <ChevronUp className="w-4 h-4" />
            </button>
            <button
              className="p-1.5 rounded-lg hover:bg-slate-100 text-text-muted hover:text-text-primary transition-colors"
              title="Review clip"
            >
              <Play className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
