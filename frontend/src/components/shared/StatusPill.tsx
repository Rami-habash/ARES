'use client'
import type { PatientStatus } from '@/types'

interface Props { status: PatientStatus }

const config = {
  'Stable': 'bg-pill-stable text-accent-green',
  'Needs Review': 'bg-pill-review text-accent-amber',
  'At Risk': 'bg-pill-risk text-accent-red',
}

export default function StatusPill({ status }: Props) {
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${config[status]}`}>
      {status}
    </span>
  )
}
