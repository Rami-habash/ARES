'use client'
import type { ExerciseMetric } from '@/types'

interface Props { metrics: ExerciseMetric[] }

const statusConfig = {
  'Good': { pill: 'bg-green-100 text-green-700', row: 'bg-diff-good' },
  'Mild issue': { pill: 'bg-amber-100 text-amber-700', row: 'bg-yellow-50' },
  'Needs correction': { pill: 'bg-red-100 text-red-700', row: 'bg-diff-bad' },
}

export default function MovementDiffTable({ metrics }: Props) {
  return (
    <div className="bg-card rounded-xl border border-border overflow-hidden shadow-sm">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border bg-slate-50">
            <th className="text-left px-4 py-3 text-xs font-semibold uppercase tracking-wider text-text-muted">Metric</th>
            <th className="text-left px-4 py-3 text-xs font-semibold uppercase tracking-wider text-text-muted">Reference</th>
            <th className="text-left px-4 py-3 text-xs font-semibold uppercase tracking-wider text-text-muted">Observed</th>
            <th className="text-left px-4 py-3 text-xs font-semibold uppercase tracking-wider text-text-muted">Status</th>
            <th className="text-left px-4 py-3 text-xs font-semibold uppercase tracking-wider text-text-muted">Feedback</th>
          </tr>
        </thead>
        <tbody>
          {metrics.map((m, i) => {
            const config = statusConfig[m.status]
            return (
              <tr key={i} className={`border-b border-border/50 ${config.row}`}>
                <td className="px-4 py-3 font-medium text-text-primary">{m.metric}</td>
                <td className="px-4 py-3 text-text-muted font-mono text-xs">{m.reference}</td>
                <td className={`px-4 py-3 font-mono text-xs ${m.status !== 'Good' ? 'font-bold text-text-primary' : 'text-text-muted'}`}>{m.observed}</td>
                <td className="px-4 py-3">
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${config.pill}`}>{m.status}</span>
                </td>
                <td className="px-4 py-3 text-xs text-text-muted">{m.feedback}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
