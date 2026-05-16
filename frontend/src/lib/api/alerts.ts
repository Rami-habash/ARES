import { USE_MOCK } from '@/lib/config'
import { MOCK_ALERTS } from '@/data/alerts'
import type { Alert } from '@/types'

export async function getAlerts(): Promise<Alert[]> {
  if (USE_MOCK) return MOCK_ALERTS
  const res = await fetch(`${process.env.NEXT_PUBLIC_API_BASE}/alerts`)
  return res.json()
}
