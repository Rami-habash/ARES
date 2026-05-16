'use client'
import { useCoaching } from '@/hooks/useCoaching'

interface Props {
  patientId:   string
  patientName: string
}

export default function CoachingPanel({ patientId, patientName }: Props) {
  const coaching = useCoaching(patientId)

  return (
    <div className="bg-card rounded-xl border border-border p-5 shadow-sm flex flex-col gap-4">
      <div>
        <p className="text-xs font-semibold uppercase tracking-widest text-text-muted mb-1">AI Coach</p>
        <h3 className="font-semibold text-text-primary">Coaching — {patientName}</h3>
      </div>

      {coaching ? (
        <div className="rounded-lg bg-accent-green/10 border border-accent-green/30 p-4">
          <p className="text-sm font-medium text-accent-green leading-relaxed">{coaching.text}</p>
          <p className="text-xs text-text-muted mt-2">
            {new Date(coaching.ts).toLocaleTimeString()}
          </p>
        </div>
      ) : (
        <p className="text-sm text-text-muted italic">Waiting for live coaching…</p>
      )}
    </div>
  )
}
