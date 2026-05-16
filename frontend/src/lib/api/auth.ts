import { API_BASE, USE_MOCK } from '@/lib/config'

export interface AuthResponse {
  access_token: string
  token_type: string
  role: 'admin' | 'patient'
  name: string
  user_id: number
}

export interface UserMe {
  id: number
  email: string
  name: string
  role: 'admin' | 'patient'
  nemo_patient_id: string | null
}

// ── Token storage ─────────────────────────────────────────────────────────────

export function saveToken(token: string, role: string): void {
  if (typeof window === 'undefined') return
  localStorage.setItem('ares_token', token)
  localStorage.setItem('ares_role', role)
}

export function getToken(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem('ares_token')
}

export function getRole(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem('ares_role')
}

export function savePatientId(id: string): void {
  if (typeof window === 'undefined') return
  localStorage.setItem('ares_patient_id', id)
}

export function getPatientId(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem('ares_patient_id')
}

export function clearToken(): void {
  if (typeof window === 'undefined') return
  localStorage.removeItem('ares_token')
  localStorage.removeItem('ares_role')
  localStorage.removeItem('ares_patient_id')
}

export function authHeaders(): HeadersInit {
  const token = getToken()
  return {
    'ngrok-skip-browser-warning': 'true',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }
}

// ── Auth endpoints ────────────────────────────────────────────────────────────

export async function login(email: string, password: string): Promise<AuthResponse> {
  if (USE_MOCK) {
    // Demo mock — any credentials accepted, role determined by email prefix
    const role = email.startsWith('admin') ? 'admin' : 'patient'
    const mock: AuthResponse = { access_token: 'mock-token', token_type: 'bearer', role, name: 'Demo User', user_id: 0 }
    saveToken(mock.access_token, mock.role)
    return mock
  }
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'ngrok-skip-browser-warning': 'true' },
    body: JSON.stringify({ email, password }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail ?? 'Login failed')
  }
  const data: AuthResponse = await res.json()
  saveToken(data.access_token, data.role)
  return data
}

export async function register(
  email: string,
  password: string,
  name: string,
  role: 'admin' | 'patient' = 'patient',
): Promise<AuthResponse> {
  if (USE_MOCK) {
    const mock: AuthResponse = { access_token: 'mock-token', token_type: 'bearer', role, name, user_id: 0 }
    saveToken(mock.access_token, mock.role)
    return mock
  }
  const res = await fetch(`${API_BASE}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'ngrok-skip-browser-warning': 'true' },
    body: JSON.stringify({ email, password, name, role }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail ?? 'Registration failed')
  }
  const data: AuthResponse = await res.json()
  saveToken(data.access_token, data.role)
  return data
}

export function googleLoginUrl(): string {
  return `${API_BASE}/auth/google`
}

export async function getMe(): Promise<UserMe> {
  if (USE_MOCK) {
    return { id: 0, email: 'demo@solstice.health', name: 'Demo User', role: 'admin', nemo_patient_id: null }
  }
  const res = await fetch(`${API_BASE}/users/me`, { headers: { ...authHeaders() } })
  if (!res.ok) throw new Error('Not authenticated')
  return res.json()
}
