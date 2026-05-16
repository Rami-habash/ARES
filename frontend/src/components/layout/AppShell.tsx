'use client'
import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import Sidebar from './Sidebar'
import DashboardView from '@/components/views/DashboardView'
import RoomMonitorView from '@/components/views/RoomMonitorView'
import PatientsView from '@/components/views/PatientsView'
import ExerciseDetailView from '@/components/views/ExerciseDetailView'
import AlertsView from '@/components/views/AlertsView'
import ReportsView from '@/components/views/ReportsView'
import AIAssistantView from '@/components/views/AIAssistantView'
import SettingsView from '@/components/views/SettingsView'
import { useDemoState } from '@/hooks/useDemoState'
import type { NavItem } from '@/types'

export default function AppShell() {
  const [activeView, setActiveView] = useState<NavItem>('dashboard')
  const [selectedPatient, setSelectedPatient] = useState<string | null>('P-102')
  const demo = useDemoState()

  const views: Record<NavItem, React.ReactNode> = {
    dashboard: <DashboardView setActiveView={setActiveView} setSelectedPatient={setSelectedPatient} demo={demo} />,
    'room-monitor': <RoomMonitorView />,
    patients: <PatientsView setActiveView={setActiveView} setSelectedPatient={setSelectedPatient} demo={demo} />,
    exercise: <ExerciseDetailView />,
    alerts: <AlertsView />,
    reports: <ReportsView selectedPatient={selectedPatient} />,
    'ai-assistant': <AIAssistantView />,
    settings: <SettingsView demo={demo} />,
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar active={activeView} onNav={setActiveView} />
      <main className="flex-1 overflow-auto bg-workspace">
        <AnimatePresence mode="wait">
          <motion.div
            key={activeView}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.18 }}
            className="h-full"
          >
            {views[activeView]}
          </motion.div>
        </AnimatePresence>
      </main>
    </div>
  )
}
