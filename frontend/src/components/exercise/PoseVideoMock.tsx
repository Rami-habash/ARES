'use client'
import { motion } from 'framer-motion'

const landmarks = [
  { id: 'nose', x: 50, y: 10 },
  { id: 'l-shoulder', x: 38, y: 28 },
  { id: 'r-shoulder', x: 62, y: 28 },
  { id: 'l-elbow', x: 30, y: 44 },
  { id: 'r-elbow', x: 70, y: 44 },
  { id: 'l-wrist', x: 26, y: 58 },
  { id: 'r-wrist', x: 74, y: 58 },
  { id: 'l-hip', x: 41, y: 56 },
  { id: 'r-hip', x: 59, y: 56 },
  { id: 'l-knee', x: 38, y: 74 },
  { id: 'r-knee', x: 62, y: 74 },
  { id: 'l-ankle', x: 36, y: 90 },
  { id: 'r-ankle', x: 64, y: 90 },
]

const connections = [
  ['nose', 'l-shoulder'], ['nose', 'r-shoulder'],
  ['l-shoulder', 'r-shoulder'],
  ['l-shoulder', 'l-elbow'], ['l-elbow', 'l-wrist'],
  ['r-shoulder', 'r-elbow'], ['r-elbow', 'r-wrist'],
  ['l-shoulder', 'l-hip'], ['r-shoulder', 'r-hip'],
  ['l-hip', 'r-hip'],
  ['l-hip', 'l-knee'], ['l-knee', 'l-ankle'],
  ['r-hip', 'r-knee'], ['r-knee', 'r-ankle'],
]

const problemJoints = new Set(['r-knee', 'r-ankle'])

export default function PoseVideoMock() {
  const lm = Object.fromEntries(landmarks.map(l => [l.id, l]))

  return (
    <div className="relative bg-[#1a2333] rounded-xl overflow-hidden aspect-video">
      <svg viewBox="0 0 100 100" className="w-full h-full" preserveAspectRatio="xMidYMid meet">
        {connections.map(([a, b]) => {
          const p1 = lm[a], p2 = lm[b]
          const isIssue = problemJoints.has(a) || problemJoints.has(b)
          return (
            <line
              key={`${a}-${b}`}
              x1={p1.x} y1={p1.y} x2={p2.x} y2={p2.y}
              stroke={isIssue ? '#dc2626' : '#16a34a'}
              strokeWidth="0.8"
              strokeOpacity="0.8"
            />
          )
        })}
        {landmarks.map(lmk => (
          <motion.circle
            key={lmk.id}
            cx={lmk.x}
            cy={lmk.y}
            r={1.2}
            fill={problemJoints.has(lmk.id) ? '#dc2626' : '#ffffff'}
            animate={{ cy: [lmk.y - 0.5, lmk.y + 0.5, lmk.y - 0.5] }}
            transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut', delay: Math.random() * 1 }}
          />
        ))}
      </svg>

      <div className="absolute top-3 left-3 space-y-1">
        <div className="bg-black/60 text-white text-xs px-2 py-1 rounded font-mono">
          REP 8 / 10
        </div>
        <div className="bg-accent-amber/80 text-white text-xs px-2 py-1 rounded font-mono">
          ECCENTRIC PHASE
        </div>
      </div>

      <div className="absolute top-3 right-3">
        <div className="bg-black/60 text-white text-xs px-2 py-1 rounded font-mono">
          94% conf.
        </div>
      </div>

      <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/60 to-transparent p-3">
        <p className="text-white/60 text-xs font-mono">Bodyweight Squat · Maya Patel · P-102</p>
      </div>
    </div>
  )
}
