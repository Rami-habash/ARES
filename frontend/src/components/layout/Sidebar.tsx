'use client'
import { useRouter } from 'next/navigation'
import { LayoutDashboard, Monitor, Users, Activity, AlertTriangle, FileText, MessageSquare, Settings, LogOut } from 'lucide-react'
import LiveDot from '@/components/shared/LiveDot'
import type { NavItem } from '@/types'

function SunIcon({ size = 18 }: { size?: number }) {
  const r = size / 2
  const innerR = r * 0.32
  const outerR = r * 0.46
  const rayLen = r * 0.18
  const rayCount = 12
  const rays = Array.from({ length: rayCount }, (_, i) => {
    const rad = (i * 360 / rayCount * Math.PI) / 180
    return {
      x1: r + Math.cos(rad) * (outerR + 1),
      y1: r + Math.sin(rad) * (outerR + 1),
      x2: r + Math.cos(rad) * (outerR + rayLen),
      y2: r + Math.sin(rad) * (outerR + rayLen),
    }
  })
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} fill="none">
      <circle cx={r} cy={r} r={innerR} fill="currentColor" />
      {rays.map((ray, i) => (
        <line key={i} x1={ray.x1} y1={ray.y1} x2={ray.x2} y2={ray.y2}
          stroke="currentColor" strokeWidth={i % 2 === 0 ? 1.4 : 0.9} strokeLinecap="round" />
      ))}
    </svg>
  )
}

interface Props {
  active: NavItem
  onNav: (item: NavItem) => void
}

const navItems: { id: NavItem; label: string; icon: React.ElementType; live?: boolean }[] = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'room-monitor', label: 'Room Monitor', icon: Monitor, live: true },
  { id: 'patients', label: 'Patients', icon: Users },
  { id: 'exercise', label: 'Exercise Detail', icon: Activity },
  { id: 'alerts', label: 'Alerts', icon: AlertTriangle },
  { id: 'reports', label: 'Reports', icon: FileText },
  { id: 'ai-assistant', label: 'AI Assistant', icon: MessageSquare },
  { id: 'settings', label: 'Settings', icon: Settings },
]

export default function Sidebar({ active, onNav }: Props) {
  const router = useRouter()

  return (
    <div className="w-64 h-screen flex flex-col flex-shrink-0" style={{ background: '#1a1208' }}>
      <div className="px-6 py-6 border-b border-white/10">
        <div className="flex items-center gap-2">
          <div className="text-[#e8622c]">
            <SunIcon size={22} />
          </div>
          <span className="text-white font-bold text-lg tracking-wide">SOLSTICE</span>
        </div>
        <p className="text-white/40 text-xs mt-1 tracking-wider">REHAB INTELLIGENCE</p>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-1">
        {navItems.map(item => {
          const Icon = item.icon
          const isActive = active === item.id
          return (
            <button
              key={item.id}
              onClick={() => onNav(item.id)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors ${
                isActive
                  ? 'text-white'
                  : 'text-white/50 hover:text-white hover:bg-white/5'
              }`}
              style={isActive ? { background: 'rgba(232,98,44,0.18)' } : {}}
            >
              <Icon className={`w-4 h-4 flex-shrink-0 ${isActive ? 'text-[#e8622c]' : ''}`} />
              <span className="flex-1 text-left">{item.label}</span>
              {item.live && <LiveDot />}
            </button>
          )
        })}
      </nav>

      <div className="px-3 py-4 border-t border-white/10">
        <button
          onClick={() => router.push('/')}
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-white/40 hover:text-white/70 text-sm transition-colors"
        >
          <LogOut className="w-4 h-4" />
          <span>Sign Out</span>
        </button>
      </div>
    </div>
  )
}
