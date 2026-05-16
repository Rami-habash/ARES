'use client'
import SectionLabel from '@/components/shared/SectionLabel'
import StatCard from '@/components/dashboard/StatCard'
import PatientCard from '@/components/dashboard/PatientCard'
import EventTimeline from '@/components/dashboard/EventTimeline'
import FacilityRiskPanel from '@/components/dashboard/FacilityRiskPanel'
import { useSimulatedUpdates } from '@/hooks/useSimulatedUpdates'
import { EVENTS_TIMELINE } from '@/data/exercises'
import type { NavItem } from '@/types'

interface Props {
  setActiveView: (v: NavItem) => void
  setSelectedPatient: (id: string) => void
  demo: { liveUpdates: boolean }
}

export default function DashboardView({ setActiveView, setSelectedPatient, demo }: Props) {
  const patients = useSimulatedUpdates(demo.liveUpdates)
  const avgFormScore = patients.reduce((s, p) => s + p.formScore, 0) / patients.length

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <div className="mb-8">
        <SectionLabel>Rehab Command Center</SectionLabel>
        <h1 className="text-3xl font-bold text-text-primary">Solstice Rehab Room</h1>
        <p className="text-text-muted mt-1">Room A · 4 patients active · {new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}</p>
      </div>

      <div className="grid grid-cols-5 gap-4 mb-8">
        <StatCard label="Patients Monitored" value={patients.length} trend="All zones active" />
        <StatCard label="Active Sessions" value={3} trend="1 in cooldown" />
        <StatCard label="Open Alerts" value={5} color="text-accent-red" trend="2 critical" />
        <StatCard label="Avg Form Score" value={avgFormScore} unit="/100" trend="↑ 3pts from last session" />
        <StatCard label="Exercises Completed" value={24} trend="Today" />
      </div>

      <div className="grid grid-cols-3 gap-6 mb-8">
        <div className="col-span-2 space-y-4">
          <SectionLabel>Active Patients</SectionLabel>
          <div className="grid grid-cols-2 gap-4">
            {patients.map(p => (
              <PatientCard
                key={p.id}
                patient={p}
                setActiveView={setActiveView}
                setSelectedPatient={setSelectedPatient}
              />
            ))}
          </div>
        </div>
        <div>
          <SectionLabel>Risk Overview</SectionLabel>
          <div className="mt-1">
            <FacilityRiskPanel patients={patients} />
          </div>
        </div>
      </div>

      <div>
        <SectionLabel>Live Event Feed</SectionLabel>
        <div className="bg-card rounded-xl border border-border p-5 shadow-sm mt-1">
          <EventTimeline events={EVENTS_TIMELINE} />
        </div>
      </div>
    </div>
  )
}
