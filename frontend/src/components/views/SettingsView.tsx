'use client'
import SectionLabel from '@/components/shared/SectionLabel'
import DemoControls from '@/components/settings/DemoControls'

interface Props {
  demo: {
    liveUpdates: boolean
    setLiveUpdates: (v: boolean) => void
    riskEvents: boolean
    setRiskEvents: (v: boolean) => void
    skeletonOverlay: boolean
    setSkeletonOverlay: (v: boolean) => void
    modelConfidence: number
    setModelConfidence: (v: number) => void
  }
}

export default function SettingsView({ demo }: Props) {
  return (
    <div className="p-8 max-w-7xl mx-auto">
      <div className="mb-6">
        <SectionLabel>Configuration</SectionLabel>
        <h1 className="text-2xl font-bold text-text-primary">Settings</h1>
      </div>
      <DemoControls demo={demo} />
    </div>
  )
}
