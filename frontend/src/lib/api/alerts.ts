import { API_BASE, USE_MOCK } from '@/lib/config'
import { MOCK_ALERTS } from '@/data/alerts'
import { authHeaders } from '@/lib/api/auth'
import type { Alert } from '@/types'

export async function getAlerts(): Promise<Alert[]> {
  if (USE_MOCK) return MOCK_ALERTS
  const res = await fetch(`${API_BASE}/alerts`, { headers: authHeaders() })
  if (!res.ok) return []
  const data = await res.json()
  return (data.alerts ?? []) as Alert[]
}

export async function dismissAlert(id: string): Promise<void> {
  if (USE_MOCK) return
  await fetch(`${API_BASE}/alerts/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ status: 'Dismissed' }),
  })
}

export async function escalateAlert(id: string): Promise<void> {
  if (USE_MOCK) return
  await fetch(`${API_BASE}/alerts/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ status: 'Escalated' }),
  })
}
