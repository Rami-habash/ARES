'use client'
import { motion } from 'framer-motion'
import type { Patient } from '@/types'

interface Props {
  patient: Patient
  position: { top: string; left: string; width: string; height: string }
  selected: boolean
  onClick: () => void
}

const statusColor: Record<string, string> = {
  'Stable': 'border-accent-green',
  'Needs Review': 'border-accent-amber',
  'At Risk': 'border-accent-red',
}

const statusBg: Record<string, string> = {
  'Stable': 'bg-accent-green',
  'Needs Review': 'bg-accent-amber',
  'At Risk': 'bg-accent-red',
}

export default function BoundingBox({ patient, position, selected, onClick }: Props) {
  return (
    <motion.div
      className={`absolute border-2 cursor-pointer rounded-sm ${statusColor[patient.status]} ${selected ? 'ring-2 ring-white/50' : ''}`}
      style={position}
      onClick={onClick}
      animate={selected ? { scale: [1, 1.02, 1] } : { scale: 1 }}
      transition={{ duration: 0.6, repeat: selected ? Infinity : 0 }}
    >
      <div className={`absolute -top-5 left-0 right-0 text-white text-xs px-1 py-0.5 flex justify-between ${statusBg[patient.status]}`}>
        <span className="font-bold">{patient.name.split(' ')[0]}</span>
        <span>{patient.id}</span>
      </div>
      <div className="absolute -bottom-5 left-0 right-0 bg-black/70 text-white text-xs px-1 py-0.5 flex justify-between">
        <span>{patient.currentExercise}</span>
        <span>{Math.round(patient.trackingConfidence)}%</span>
      </div>
    </motion.div>
  )
}
