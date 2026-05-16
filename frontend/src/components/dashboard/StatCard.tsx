'use client'
import { useEffect, useState } from 'react'

interface Props {
  label: string
  value: number | string
  unit?: string
  trend?: string
  color?: string
  live?: boolean
}

export default function StatCard({ label, value, unit, trend, color = 'text-text-primary' }: Props) {
  const [displayed, setDisplayed] = useState(value)

  useEffect(() => {
    setDisplayed(value)
  }, [value])

  return (
    <div className="bg-card rounded-xl border border-border p-5 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-widest text-text-muted mb-2">{label}</p>
      <div className="flex items-end gap-1">
        <span className={`text-3xl font-bold ${color}`}>{typeof displayed === 'number' ? Math.round(displayed as number) : displayed}</span>
        {unit && <span className="text-text-muted text-sm mb-1">{unit}</span>}
      </div>
      {trend && <p className="text-xs text-text-muted mt-1">{trend}</p>}
    </div>
  )
}
