'use client'
import { useEffect, useRef } from 'react'
import type { LiveFrame } from '@/hooks/useLiveSecurityStream'

interface Props {
  latestFrame: LiveFrame | null
  sourceSize: { width: number; height: number } | null
  selectedPatientId: string | null
  onSelectPatient?: (id: string | null) => void
  filterPatientId?: string | null
  showKeypoints?: boolean
  mjpegSrc?: string
}

// MediaPipe Pose connections (matches CV/keypoint_extraction.py CONNECTIONS).
const SKELETON_EDGES: [number, number][] = [
  [11, 12], [11, 13], [13, 15], [12, 14], [14, 16],
  [11, 23], [12, 24], [23, 24],
  [23, 25], [25, 27], [24, 26], [26, 28],
  [0, 11],  [0, 12],
]
const SKELETON_NODES = [0, 11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28]

const HUES = [200, 50, 320, 130, 20, 280]
const colorFor = (tid: number) => `hsl(${HUES[tid % HUES.length]}, 80%, 60%)`

// Visible-video-inside-element math for object-contain letterboxing.
function visibleVideoRect(
  elementRect: { width: number; height: number },
  src: { width: number; height: number },
) {
  const elementAspect = elementRect.width / elementRect.height
  const srcAspect = src.width / src.height
  if (srcAspect > elementAspect) {
    const renderedHeight = elementRect.width / srcAspect
    return { left: 0, top: (elementRect.height - renderedHeight) / 2, width: elementRect.width, height: renderedHeight }
  }
  const renderedWidth = elementRect.height * srcAspect
  return { left: (elementRect.width - renderedWidth) / 2, top: 0, width: renderedWidth, height: elementRect.height }
}

export default function LiveCameraCanvas({
  latestFrame,
  sourceSize,
  selectedPatientId,
  onSelectPatient,
  filterPatientId = null,
  showKeypoints = false,
  mjpegSrc = '/api/stream',
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const containerRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const draw = () => {
      const canvas = canvasRef.current
      const container = containerRef.current
      if (!canvas || !container || !sourceSize) return

      // Use clientWidth/Height (which respects inset-0 layout) instead of
      // setting style.width/height ourselves — that detaches the canvas from
      // the inset-0 positioning and pins it to top-left.
      const w = container.clientWidth
      const h = container.clientHeight
      if (w === 0 || h === 0) return

      const dpr = window.devicePixelRatio || 1
      // Resize the drawing buffer only when needed.
      if (canvas.width !== w * dpr || canvas.height !== h * dpr) {
        canvas.width = w * dpr
        canvas.height = h * dpr
      }

      const ctx = canvas.getContext('2d')
      if (!ctx) return
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.clearRect(0, 0, w, h)

      const vis = visibleVideoRect({ width: w, height: h }, sourceSize)
      const sx = vis.width / sourceSize.width
      const sy = vis.height / sourceSize.height

      const allDets = latestFrame?.dets ?? []
      const dets = filterPatientId
        ? allDets.filter(d => d.patient_id === filterPatientId)
        : allDets
      for (const det of dets) {
        const [x1, y1, x2, y2] = det.bbox
        const color = colorFor(det.track_id)
        const isSelected = det.patient_id !== null && det.patient_id === selectedPatientId

        ctx.strokeStyle = color
        ctx.lineWidth = isSelected ? 4 : 2
        ctx.strokeRect(vis.left + x1 * sx, vis.top + y1 * sy, (x2 - x1) * sx, (y2 - y1) * sy)

        const label = det.patient_id ? `${det.patient_id} (#${det.track_id})` : `#${det.track_id}`
        ctx.font = 'bold 13px ui-monospace, monospace'
        const padding = 4
        const textWidth = ctx.measureText(label).width
        const labelHeight = 18
        ctx.fillStyle = color
        ctx.fillRect(vis.left + x1 * sx, vis.top + y1 * sy - labelHeight, textWidth + padding * 2, labelHeight)
        ctx.fillStyle = '#000'
        ctx.fillText(label, vis.left + x1 * sx + padding, vis.top + y1 * sy - 5)

        if (showKeypoints && det.keypoints.length > 0) {
          // Keypoints are normalized 0–1 within the bbox crop; map to
          // canvas pixels via the same letterboxing math as the bbox.
          const bw = (x2 - x1) * sx
          const bh = (y2 - y1) * sy
          const bx = vis.left + x1 * sx
          const by = vis.top + y1 * sy
          const px = (lm: { x: number }) => bx + lm.x * bw
          const py = (lm: { y: number }) => by + lm.y * bh

          ctx.strokeStyle = '#34d399'  // emerald-400
          ctx.lineWidth = 2
          for (const [a, b] of SKELETON_EDGES) {
            const la = det.keypoints[a]
            const lb = det.keypoints[b]
            if (!la || !lb || la.visibility < 0.3 || lb.visibility < 0.3) continue
            ctx.beginPath()
            ctx.moveTo(px(la), py(la))
            ctx.lineTo(px(lb), py(lb))
            ctx.stroke()
          }
          ctx.fillStyle = '#10b981'  // emerald-500
          for (const idx of SKELETON_NODES) {
            const lm = det.keypoints[idx]
            if (!lm || lm.visibility < 0.3) continue
            ctx.beginPath()
            ctx.arc(px(lm), py(lm), 4, 0, Math.PI * 2)
            ctx.fill()
          }
        }
      }
    }

    draw()
    const observer = new ResizeObserver(draw)
    if (containerRef.current) observer.observe(containerRef.current)
    return () => observer.disconnect()
  }, [latestFrame, sourceSize, selectedPatientId, filterPatientId, showKeypoints])

  const handleClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!onSelectPatient) return
    const container = containerRef.current
    if (!container || !sourceSize || !latestFrame) return
    const rect = container.getBoundingClientRect()
    const vis = visibleVideoRect({ width: rect.width, height: rect.height }, sourceSize)
    const cx = ((e.clientX - rect.left - vis.left) / vis.width) * sourceSize.width
    const cy = ((e.clientY - rect.top - vis.top) / vis.height) * sourceSize.height
    const hit = latestFrame.dets.find(
      (d) => cx >= d.bbox[0] && cx <= d.bbox[2] && cy >= d.bbox[1] && cy <= d.bbox[3],
    )
    onSelectPatient(hit?.patient_id ?? null)
  }

  return (
    <div ref={containerRef} className="relative w-full h-full bg-black rounded-lg overflow-hidden">
      {/* MJPEG stream from CV — shows what the camera actually sees regardless of whether
          the broadcast source is the laptop webcam or a phone via WebRTC */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={mjpegSrc}
        alt="live feed"
        className="absolute inset-0 w-full h-full object-contain"
      />
      <canvas
        ref={canvasRef}
        onClick={handleClick}
        className={`absolute inset-0 w-full h-full ${onSelectPatient ? 'cursor-pointer' : ''}`}
      />
      <div className="absolute top-3 left-3 flex items-center gap-2 pointer-events-none z-10">
        <span className="w-2 h-2 bg-red-500 rounded-full animate-pulse" />
        <span className="text-white/80 text-xs font-mono">LIVE — security</span>
      </div>
      <div className="absolute bottom-3 right-3 text-white/40 text-xs font-mono pointer-events-none z-10">
        {latestFrame
          ? `${latestFrame.dets.length} person${latestFrame.dets.length === 1 ? '' : 's'} · frame ${latestFrame.frame_idx}`
          : 'no frames yet'}
      </div>
    </div>
  )
}
