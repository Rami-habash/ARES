'use client'
import { createContext, useContext } from 'react'
import { useLiveSecurityStream } from '@/hooks/useLiveSecurityStream'

type LiveStreamCtx = {
  security: ReturnType<typeof useLiveSecurityStream>
  detail: ReturnType<typeof useLiveSecurityStream>
}

const Ctx = createContext<LiveStreamCtx | null>(null)

const CV_LOCAL = process.env.NEXT_PUBLIC_CV_LOCAL ?? 'http://localhost:8001'

export function LiveStreamProvider({ children }: { children: React.ReactNode }) {
  const security = useLiveSecurityStream('security')
  // Detail stream uses localhost directly — no ngrok latency for local webcam
  const detail = useLiveSecurityStream('detail', CV_LOCAL)
  return <Ctx.Provider value={{ security, detail }}>{children}</Ctx.Provider>
}

export function useLiveStream(): LiveStreamCtx {
  const v = useContext(Ctx)
  if (!v) throw new Error('useLiveStream must be inside LiveStreamProvider')
  return v
}
