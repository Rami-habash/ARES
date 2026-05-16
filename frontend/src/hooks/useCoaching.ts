'use client'
import { useEffect, useRef, useState } from 'react'

export interface CoachingMessage {
  text: string
  ts:   number
}

export interface ThinkingMessage {
  text: string
  ts:   number
}

export interface BestGuess {
  exercise: string | null
  score:    number | null
  ts:       number
}

export interface CoachingFeed {
  coaching:  CoachingMessage | null
  thinking:  ThinkingMessage[]   // most recent first, bounded
  bestGuess: BestGuess | null
}

const WS_URL = process.env.NEXT_PUBLIC_COACHING_WS ?? 'ws://localhost:8765'
const MAX_THINKING = 40

type WsMsg =
  | { type: 'coaching';   patient_id: string; text: string }
  | { type: 'thinking';   patient_id: string; text: string }
  | { type: 'best_guess'; patient_id: string; exercise: string | null; score: number | null }
  // Pre-typed legacy payloads — treated as coaching for backwards compat.
  | { patient_id: string; text: string }

export function useCoaching(patientId: string | null): CoachingFeed {
  const [feed, setFeed] = useState<CoachingFeed>({
    coaching: null, thinking: [], bestGuess: null,
  })
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    setFeed({ coaching: null, thinking: [], bestGuess: null })
    if (!patientId) return

    let reconnectTimer: ReturnType<typeof setTimeout>
    let stopped = false

    function connect() {
      if (stopped) return
      const ws = new WebSocket(WS_URL)
      wsRef.current = ws

      ws.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data) as WsMsg
          if (data.patient_id !== patientId) return
          const now = Date.now()
          const type = 'type' in data ? data.type : 'coaching'

          if (type === 'coaching') {
            const text = (data as { text: string }).text
            setFeed(f => ({ ...f, coaching: { text, ts: now } }))
            // Speak only the agent's coaching, not trace lines.
            if (typeof window !== 'undefined' && window.speechSynthesis) {
              window.speechSynthesis.cancel()
              const utt = new SpeechSynthesisUtterance(text)
              utt.rate = 1.0
              utt.pitch = 1.0
              window.speechSynthesis.speak(utt)
            }
          } else if (type === 'thinking') {
            const text = (data as { text: string }).text
            setFeed(f => ({
              ...f,
              thinking: [{ text, ts: now }, ...f.thinking].slice(0, MAX_THINKING),
            }))
          } else if (type === 'best_guess') {
            const d = data as { exercise: string | null; score: number | null }
            setFeed(f => ({ ...f, bestGuess: { exercise: d.exercise, score: d.score, ts: now } }))
          }
        } catch {
          // ignore malformed messages
        }
      }

      ws.onclose = () => {
        if (!stopped) reconnectTimer = setTimeout(connect, 2000)
      }
    }

    connect()
    return () => {
      stopped = true
      clearTimeout(reconnectTimer)
      wsRef.current?.close()
    }
  }, [patientId])

  return feed
}
