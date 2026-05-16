'use client'
import BoundingBox from './BoundingBox'
import type { Patient } from '@/types'

interface Props {
  patients: Patient[]
  selectedId: string | null
  onSelect: (id: string) => void
}

const positions = [
  { top: '55%', left: '15%', width: '14%', height: '30%' },
  { top: '50%', left: '55%', width: '14%', height: '30%' },
  { top: '45%', left: '78%', width: '14%', height: '35%' },
  { top: '52%', left: '35%', width: '13%', height: '28%' },
]

export default function CameraCanvas({ patients, selectedId, onSelect }: Props) {
  return (
    <div className="relative w-full h-full bg-[#1a2333] rounded-lg overflow-hidden">
      <svg className="absolute inset-0 w-full h-full opacity-10" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <pattern id="grid" width="60" height="60" patternUnits="userSpaceOnUse">
            <path d="M 60 0 L 0 0 0 60" fill="none" stroke="white" strokeWidth="0.5" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#grid)" />
      </svg>

      <div className="absolute inset-0" style={{
        background: 'radial-gradient(ellipse at center, transparent 50%, rgba(0,0,0,0.6) 100%)'
      }} />

      {patients.map((patient, i) => (
        <BoundingBox
          key={patient.id}
          patient={patient}
          position={positions[i]}
          selected={selectedId === patient.id}
          onClick={() => onSelect(patient.id)}
        />
      ))}

      <div className="absolute bottom-3 right-3 text-white/20 text-xs font-mono">ROOM A — WIDE</div>
      <div className="absolute top-3 left-3 flex items-center gap-2">
        <span className="w-2 h-2 bg-red-500 rounded-full animate-pulse" />
        <span className="text-white/60 text-xs font-mono">LIVE</span>
      </div>
    </div>
  )
}
