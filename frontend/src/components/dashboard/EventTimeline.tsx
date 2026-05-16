'use client'
import type { SessionEvent } from '@/types'

interface Props { events: SessionEvent[] }

const typeConfig = {
  alert: { color: 'bg-accent-red', label: 'ALERT' },
  rep: { color: 'bg-accent-blue', label: 'REP' },
  phase: { color: 'bg-accent-amber', label: 'PHASE' },
  note: { color: 'bg-slate-400', label: 'NOTE' },
}

export default function EventTimeline({ events }: Props) {
  return (
    <div className="space-y-2">
      {events.map(event => {
        const config = typeConfig[event.type]
        return (
          <div key={event.id} className="flex items-start gap-3">
            <span className={`mt-0.5 inline-block w-1.5 h-1.5 rounded-full flex-shrink-0 ${config.color}`} />
            <div className="flex-1 min-w-0">
              <span className="text-xs font-bold text-text-muted mr-2">{config.label}</span>
              <span className="text-sm text-text-primary">{event.description}</span>
            </div>
            <span className="text-xs text-text-muted flex-shrink-0">{event.time}</span>
          </div>
        )
      })}
    </div>
  )
}
