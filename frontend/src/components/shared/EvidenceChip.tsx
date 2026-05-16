'use client'
interface Props { label: string; timestamp?: string }

export default function EvidenceChip({ label, timestamp }: Props) {
  return (
    <span className="inline-flex items-center gap-1 px-2 py-1 bg-slate-100 text-slate-600 text-xs rounded-md border border-slate-200 cursor-pointer hover:bg-slate-200 transition-colors">
      {timestamp && <span className="text-slate-400">{timestamp}</span>}
      {label}
    </span>
  )
}
