'use client'
import { useState } from 'react'
import SectionLabel from '@/components/shared/SectionLabel'
import LiveCameraCanvas from '@/components/room-monitor/LiveCameraCanvas'
import LiveInspector from '@/components/room-monitor/LiveInspector'
import { useLiveStream } from '@/components/providers/LiveStreamProvider'
import { useGymSessions } from '@/hooks/useGymSessions'

export default function RoomMonitorView() {
  const { security } = useLiveStream()
  const { sessions, error: sessionsError } = useGymSessions()
  const [selectedPatientId, setSelectedPatientId] = useState<string | null>(null)

  return (
    <div className="flex flex-col h-full p-6 gap-4">
      <div>
        <SectionLabel>Live Camera Feed</SectionLabel>
        <div className="flex items-center gap-3 mt-1">
          <h2 className="text-xl font-bold text-text-primary">Room Monitor</h2>
          <span className="text-xs bg-slate-200 text-slate-600 px-2 py-0.5 rounded font-mono">SECURITY</span>
          <span className="text-xs bg-slate-200 text-slate-600 px-2 py-0.5 rounded font-mono">YOLO11 + BoT-SORT</span>
          <span className="text-xs bg-slate-200 text-slate-600 px-2 py-0.5 rounded font-mono">ArUco identity</span>
        </div>
      </div>

      <div className="flex gap-4 flex-1 min-h-0">
        <div className="flex-1 min-w-0">
          <LiveCameraCanvas
            latestFrame={security.latestFrame}
            sourceSize={security.sourceSize}
            selectedPatientId={selectedPatientId}
            onSelectPatient={setSelectedPatientId}
          />
        </div>
        <div className="w-72 bg-card border border-border rounded-xl overflow-hidden">
          <LiveInspector
            sessions={sessions}
            sessionsError={sessionsError}
            selectedPatientId={selectedPatientId}
            onSelectPatient={setSelectedPatientId}
          />
        </div>
      </div>
    </div>
  )
}
