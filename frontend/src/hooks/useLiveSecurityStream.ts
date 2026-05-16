'use client'
import { useCallback, useEffect, useRef, useState } from 'react'
import { CV_BASE, CV_WS_BASE } from '@/lib/config'

// Hoisted into a Provider at AppShell so the WebRTC broadcast + bbox WS
// survive view navigation. Consumers attach `mediaStream` to their own
// <video srcObject> — a single MediaStream can drive multiple video elements.

// One MediaPipe landmark, normalized 0–1 within the bbox crop (NOT the source
// frame). Map to source-frame pixels with: x1 + lm.x * (x2 - x1).
export interface PoseLandmark {
  x:          number
  y:          number
  z:          number
  visibility: number
}

// One detection emitted by CV's /live/ws — kept minimal, no synthesised
// patient state. `patient_id` is null until the ArUco binding fires.
// `keypoints` is non-empty only for bound patients on the security stream.
export interface LiveDetection {
  stream:       string
  frame_idx:    number
  timestamp_ms: number
  frame_w:      number                              // source-frame size (bbox coords are in this space)
  frame_h:      number
  track_id:     number
  patient_id:   string | null
  bbox:         [number, number, number, number]   // x1, y1, x2, y2 in source-frame pixels
  keypoints:    PoseLandmark[]
}

export interface LiveFrame {
  frame_idx:    number
  timestamp_ms: number
  dets:         LiveDetection[]
}

export type BroadcastStatus =
  | 'idle'
  | 'requesting-camera'
  | 'connecting'
  | 'broadcasting'
  | 'stopped'
  | { error: string }

// Owns:
//  - the local camera capture + WebRTC peer connection that pushes the
//    laptop webcam to CV as the "security" stream
//  - the /live/ws subscription that receives bboxes + patient_id labels
// Returns:
//  - videoRef to attach to a <video> element
//  - the most recent LiveFrame for overlay rendering
//  - source resolution so the overlay canvas can map bbox coords correctly
export function useLiveSecurityStream(stream: string = 'security', cvBase: string = CV_BASE) {
  const pcRef = useRef<RTCPeerConnection | null>(null)
  const localStreamRef = useRef<MediaStream | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  // Buffer detections by frame_idx until the next frame arrives, then flush.
  const bufferRef = useRef<{ idx: number; dets: LiveDetection[] }>({ idx: -1, dets: [] })

  const [status, setStatus] = useState<BroadcastStatus>('idle')
  const [latestFrame, setLatestFrame] = useState<LiveFrame | null>(null)
  const [sourceSize, setSourceSize] = useState<{ width: number; height: number } | null>(null)
  // Re-render consumers when the local stream appears/disappears so each
  // <video> can re-attach its srcObject.
  const [mediaStream, setMediaStream] = useState<MediaStream | null>(null)

  // ── /live/ws subscriber — keeps running even when broadcast is stopped.
  // Reconnects on close so the viewer survives a CV restart or /live/stop call.
  useEffect(() => {
    let cancelled = false
    let retry: ReturnType<typeof setTimeout> | null = null

    const connect = () => {
      const proto = CV_WS_BASE.startsWith('https') ? 'wss' : 'ws'
      const wsUrl = `${proto}://${CV_WS_BASE.replace(/^https?:\/\//, '')}/live/ws`
      console.log('[live] connecting to', wsUrl)
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => console.log('[live] WS open')
      ws.onclose = (e) => {
        console.log('[live] WS closed', e.code, e.reason)
        if (!cancelled) retry = setTimeout(connect, 1000)
      }
      ws.onerror = (e) => console.warn('[live] WS error', e)
      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data) as LiveDetection & { error?: string }
          if (msg.error || msg.stream !== stream) return
          // Source size comes with every frame — keep our cached value in sync
          // since the WebRTC stream's resolution can differ from the local
          // <video> element's videoWidth/Height.
          if (msg.frame_w && msg.frame_h) {
            setSourceSize((prev) =>
              prev && prev.width === msg.frame_w && prev.height === msg.frame_h
                ? prev
                : { width: msg.frame_w, height: msg.frame_h },
            )
          }
          const buf = bufferRef.current
          if (msg.frame_idx !== buf.idx) {
            if (buf.dets.length) {
              setLatestFrame({
                frame_idx:    buf.idx,
                timestamp_ms: buf.dets[0].timestamp_ms,
                dets:         buf.dets,
              })
            }
            buf.idx = msg.frame_idx
            buf.dets = []
          }
          buf.dets.push(msg)
        } catch {
          /* ignore non-JSON */
        }
      }
    }

    connect()
    return () => {
      cancelled = true
      if (retry) clearTimeout(retry)
      wsRef.current?.close()
      wsRef.current = null
    }
  }, [stream])

  // No-op now that source size comes from CV via frame_w/frame_h on every
  // detection (the WebRTC stream resolution can differ from the local
  // <video> element's natural size, so we don't trust videoWidth).
  const handleVideoMetadata = useCallback(() => {}, [])

  const start = useCallback(async () => {
    try {
      // Make sure CV has a LiveSession ready before we offer it a track.
      // 409 means "session already running" which is fine — we just attach.
      const startResp = await fetch(`${cvBase}/live/start_webrtc`, { method: 'POST' })
      if (!startResp.ok && startResp.status !== 409) {
        setStatus({ error: `start_webrtc failed: ${await startResp.text()}` })
        return
      }

      setStatus('requesting-camera')
      const local = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 1280 }, height: { ideal: 720 }, frameRate: { ideal: 30 } },
        audio: false,
      })
      localStreamRef.current = local
      setMediaStream(local)

      setStatus('connecting')
      const pc = new RTCPeerConnection({ iceServers: [{ urls: 'stun:stun.l.google.com:19302' }] })
      pcRef.current = pc
      local.getTracks().forEach((t) => pc.addTrack(t, local))

      const offer = await pc.createOffer()
      await pc.setLocalDescription(offer)
      await new Promise<void>((resolve) => {
        if (pc.iceGatheringState === 'complete') return resolve()
        pc.addEventListener('icegatheringstatechange', () => {
          if (pc.iceGatheringState === 'complete') resolve()
        })
      })

      const resp = await fetch(`${cvBase}/webrtc/offer`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ stream, sdp: pc.localDescription!.sdp, type: pc.localDescription!.type }),
      })
      if (!resp.ok) {
        setStatus({ error: `offer failed: ${await resp.text()}` })
        return
      }
      const answer = await resp.json()
      await pc.setRemoteDescription(answer)
      setStatus('broadcasting')
    } catch (exc) {
      setStatus({ error: (exc as Error).message ?? 'broadcast failed' })
    }
  }, [stream])

  const stop = useCallback(() => {
    pcRef.current?.close()
    pcRef.current = null
    localStreamRef.current?.getTracks().forEach((t) => t.stop())
    localStreamRef.current = null
    setMediaStream(null)
    setStatus('stopped')
  }, [])

  // Clean up on unmount.
  useEffect(() => () => stop(), [stop])

  return { mediaStream, status, start, stop, latestFrame, sourceSize, handleVideoMetadata }
}
