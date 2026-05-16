'use client'
import { createContext, useContext } from 'react'
import { useLiveSecurityStream } from '@/hooks/useLiveSecurityStream'

type LiveStreamCtx = ReturnType<typeof useLiveSecurityStream>

const Ctx = createContext<LiveStreamCtx | null>(null)

export function LiveStreamProvider({ children }: { children: React.ReactNode }) {
  const live = useLiveSecurityStream('security')
  return <Ctx.Provider value={live}>{children}</Ctx.Provider>
}

export function useLiveStream(): LiveStreamCtx {
  const v = useContext(Ctx)
  if (!v) throw new Error('useLiveStream must be inside LiveStreamProvider')
  return v
}
