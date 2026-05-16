'use client'
import { useEffect, useRef, useState } from 'react'

export interface CoachingMessage {
  patient_id: string
  text: string
  ts: number
}

const WS_URL = process.env.NEXT_PUBLIC_COACHING_WS ?? 'ws://localhost:8765'

export function useCoaching() {
  const [latest, setLatest] = useState<CoachingMessage | null>(null)
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    let reconnectTimer: ReturnType<typeof setTimeout>

    function connect() {
      const ws = new WebSocket(WS_URL)
      wsRef.current = ws

      ws.onmessage = (e) => {
        try {
          const msg: CoachingMessage = { ...JSON.parse(e.data), ts: Date.now() }
          setLatest(msg)
          if (typeof window !== 'undefined' && window.speechSynthesis) {
            window.speechSynthesis.cancel()
            const utt = new SpeechSynthesisUtterance(msg.text)
            utt.rate = 1.0
            utt.pitch = 1.0
            window.speechSynthesis.speak(utt)
          }
        } catch {
          // ignore malformed messages
        }
      }

      ws.onclose = () => {
        reconnectTimer = setTimeout(connect, 2000)
      }
    }

    connect()
    return () => {
      clearTimeout(reconnectTimer)
      wsRef.current?.close()
    }
  }, [])

  return latest
}
