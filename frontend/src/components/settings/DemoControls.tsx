'use client'

interface DemoState {
  liveUpdates: boolean
  setLiveUpdates: (v: boolean) => void
  riskEvents: boolean
  setRiskEvents: (v: boolean) => void
  skeletonOverlay: boolean
  setSkeletonOverlay: (v: boolean) => void
  modelConfidence: number
  setModelConfidence: (v: number) => void
}

interface Props { demo: DemoState }

function Toggle({ label, value, onChange }: { label: string; value: boolean; onChange: (v: boolean) => void }) {
  return (
    <div className="flex items-center justify-between py-3 border-b border-border last:border-0">
      <span className="text-sm text-text-primary">{label}</span>
      <button
        onClick={() => onChange(!value)}
        className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${value ? 'bg-accent-blue' : 'bg-slate-200'}`}
      >
        <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform shadow ${value ? 'translate-x-6' : 'translate-x-1'}`} />
      </button>
    </div>
  )
}

export default function DemoControls({ demo }: Props) {
  return (
    <div className="bg-card rounded-xl border border-border p-6 shadow-sm max-w-lg">
      <p className="text-xs font-semibold uppercase tracking-widest text-text-muted mb-4">Demo Controls</p>
      <Toggle label="Live Updates" value={demo.liveUpdates} onChange={demo.setLiveUpdates} />
      <Toggle label="Risk Event Generation" value={demo.riskEvents} onChange={demo.setRiskEvents} />
      <Toggle label="Skeleton Overlay" value={demo.skeletonOverlay} onChange={demo.setSkeletonOverlay} />

      <div className="py-3 border-b border-border">
        <div className="flex justify-between text-sm mb-2">
          <span className="text-text-primary">Model Confidence Threshold</span>
          <span className="text-text-muted font-mono">{demo.modelConfidence}%</span>
        </div>
        <input
          type="range"
          min={50}
          max={100}
          value={demo.modelConfidence}
          onChange={e => demo.setModelConfidence(Number(e.target.value))}
          className="w-full accent-accent-blue"
        />
      </div>

      <div className="pt-3">
        <button
          onClick={() => window.location.reload()}
          className="px-4 py-2 bg-slate-100 text-text-muted rounded-lg text-sm font-medium hover:bg-slate-200 transition-colors"
        >
          Reset Mock Data
        </button>
      </div>
    </div>
  )
}
