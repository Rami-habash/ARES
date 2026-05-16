'use client'
import { useEffect, useState } from 'react'

export interface CoachingMessage {
  patient_id: string
  text: string
  ts: string
}

const MAX_MESSAGES = 50
const WS_URL = 'ws://localhost:8765'

export function useCoachingFeed() {
  const [messages, setMessages] = useState<CoachingMessage[]>([])

  useEffect(() => {
    let ws: WebSocket | null = null
    let stopped = false

    const connect = () => {
      if (stopped) return
      ws = new WebSocket(WS_URL)

      ws.onmessage = (evt) => {
        try {
          const data = JSON.parse(evt.data) as { patient_id: string; text: string }
          const msg: CoachingMessage = {
            patient_id: data.patient_id,
            text: data.text,
            ts: new Date().toLocaleTimeString(),
          }
          setMessages((prev) => [msg, ...prev].slice(0, MAX_MESSAGES))
        } catch {
          // ignore malformed messages
        }
      }

      ws.onclose = () => {
        if (!stopped) setTimeout(connect, 2000)
      }
    }

    connect()
    return () => {
      stopped = true
      ws?.close()
    }
  }, [])

  return { messages }
}