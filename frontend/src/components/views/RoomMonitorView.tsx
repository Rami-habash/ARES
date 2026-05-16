'use client'
import { useState } from 'react'
import SectionLabel from '@/components/shared/SectionLabel'
import CameraCanvas from '@/components/room-monitor/CameraCanvas'
import PatientInspector from '@/components/room-monitor/PatientInspector'
import { useSimulatedUpdates } from '@/hooks/useSimulatedUpdates'
import type { NavItem } from '@/types'

interface Props {
  demo: { liveUpdates: boolean }
  selectedPatient: string | null
  setSelectedPatient: (id: string) => void
  setActiveView: (v: NavItem) => void
}

export default function RoomMonitorView({ demo, selectedPatient, setSelectedPatient }: Props) {
  const patients = useSimulatedUpdates(demo.liveUpdates)
  const [localSelected, setLocalSelected] = useState<string | null>(selectedPatient)

  const selected = patients.find(p => p.id === localSelected) ?? null

  const handleSelect = (id: string) => {
    setLocalSelected(id)
    setSelectedPatient(id)
  }

  return (
    <div className="flex flex-col h-full p-6 gap-4">
      <div>
        <SectionLabel>Live Camera Feed</SectionLabel>
        <div className="flex items-center gap-3 mt-1">
          <h2 className="text-xl font-bold text-text-primary">Room Monitor A</h2>
          <span className="text-xs bg-slate-200 text-slate-600 px-2 py-0.5 rounded font-mono">WIDE ANGLE</span>
          <span className="text-xs bg-slate-200 text-slate-600 px-2 py-0.5 rounded font-mono">MediaPipe</span>
          <span className="text-xs bg-slate-200 text-slate-600 px-2 py-0.5 rounded font-mono">ByteTrack</span>
        </div>
      </div>

      <div className="flex gap-4 flex-1 min-h-0">
        <div className="flex-1">
          <CameraCanvas
            patients={patients}
            selectedId={localSelected}
            onSelect={handleSelect}
          />
        </div>
        <div className="w-72 bg-card border border-border rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-border">
            <p className="text-xs font-semibold uppercase tracking-widest text-text-muted">Patient Inspector</p>
          </div>
          <PatientInspector patient={selected} />
        </div>
      </div>
    </div>
  )
}
