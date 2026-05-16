'use client'
import { useState } from 'react'

export function useDemoState() {
  const [liveUpdates, setLiveUpdates] = useState(true)
  const [riskEvents, setRiskEvents] = useState(true)
  const [skeletonOverlay, setSkeletonOverlay] = useState(true)
  const [modelConfidence, setModelConfidence] = useState(85)

  return {
    liveUpdates, setLiveUpdates,
    riskEvents, setRiskEvents,
    skeletonOverlay, setSkeletonOverlay,
    modelConfidence, setModelConfidence,
  }
}
