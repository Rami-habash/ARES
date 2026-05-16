'use client'
interface Props {
  patientName: string
}

const cues = [
  { priority: 'High', cue: 'Cue right knee out — "push knee toward pinky toe"' },
  { priority: 'Med', cue: 'Slow the descent — 3 seconds down' },
  { priority: 'Low', cue: 'Ankle mobility — try heel-elevated variation' },
]

export default function CoachingPanel({ patientName }: Props) {
  return (
    <div className="bg-card rounded-xl border border-border p-5 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-widest text-text-muted mb-1">AI Coach</p>
      <h3 className="font-semibold text-text-primary mb-4">Coaching Cues — {patientName}</h3>
      <div className="space-y-3">
        {cues.map((c, i) => (
          <div key={i} className="flex items-start gap-3">
            <span className={`text-xs font-bold px-2 py-0.5 rounded flex-shrink-0 ${
              c.priority === 'High' ? 'bg-red-100 text-red-700' :
              c.priority === 'Med' ? 'bg-amber-100 text-amber-700' :
              'bg-slate-100 text-slate-600'
            }`}>{c.priority}</span>
            <p className="text-sm text-text-primary">{c.cue}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
