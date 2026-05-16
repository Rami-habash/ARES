'use client'
import { useEffect, useRef } from 'react'
import type { LiveFrame } from '@/hooks/useLiveSecurityStream'

interface Props {
  videoRef: React.RefObject<HTMLVideoElement | null>
  onVideoMetadata: () => void
  latestFrame: LiveFrame | null
  sourceSize: { width: number; height: number } | null
  selectedPatientId: string | null
  onSelectPatient: (id: string | null) => void
}

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
  videoRef,
  onVideoMetadata,
  latestFrame,
  sourceSize,
  selectedPatientId,
  onSelectPatient,
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

      const dets = latestFrame?.dets ?? []
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
      }
    }

    draw()
    const observer = new ResizeObserver(draw)
    if (containerRef.current) observer.observe(containerRef.current)
    return () => observer.disconnect()
  }, [latestFrame, sourceSize, selectedPatientId])

  const handleClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
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
      <video
        ref={videoRef}
        onLoadedMetadata={onVideoMetadata}
        autoPlay
        muted
        playsInline
        className="absolute inset-0 w-full h-full object-contain"
      />
      <canvas
        ref={canvasRef}
        onClick={handleClick}
        className="absolute inset-0 w-full h-full cursor-pointer"
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
