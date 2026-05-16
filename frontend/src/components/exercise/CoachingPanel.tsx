'use client'
import { useCoaching } from '@/hooks/useCoaching'

interface Props {
  patientId:   string
  patientName: string
}

export default function CoachingPanel({ patientId, patientName }: Props) {
  const { coaching, thinking, bestGuess } = useCoaching(patientId)

  return (
    <div className="bg-card rounded-xl border border-border p-5 shadow-sm flex flex-col gap-4">
      <div>
        <p className="text-xs font-semibold uppercase tracking-widest text-text-muted mb-1">AI Coach</p>
        <h3 className="font-semibold text-text-primary">Coaching — {patientName}</h3>
      </div>

      <div className="rounded-lg border border-border bg-slate-50 px-3 py-2">
        <p className="text-[10px] font-semibold uppercase tracking-widest text-text-muted">Best guess</p>
        {bestGuess && bestGuess.exercise ? (
          <p className="text-sm font-mono mt-0.5">
            <span className="font-semibold text-text-primary">{bestGuess.exercise}</span>
            {typeof bestGuess.score === 'number' && (
              <span className="text-text-muted ml-2">{bestGuess.score.toFixed(2)}</span>
            )}
          </p>
        ) : (
          <p className="text-sm text-text-muted italic mt-0.5">—</p>
        )}
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

      <div>
        <p className="text-[10px] font-semibold uppercase tracking-widest text-text-muted mb-1">Pipeline activity</p>
        <div className="rounded-lg border border-border bg-slate-900/95 text-slate-100 font-mono text-[11px] leading-relaxed max-h-60 overflow-auto p-2">
          {thinking.length === 0 ? (
            <p className="text-slate-400 italic">no activity yet</p>
          ) : (
            thinking.map((t) => (
              <div key={t.ts} className="flex gap-2">
                <span className="text-slate-500 shrink-0">
                  {new Date(t.ts).toLocaleTimeString([], { hour12: false })}
                </span>
                <span className="break-words">{t.text}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
