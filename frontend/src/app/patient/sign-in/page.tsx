'use client'
import { useEffect, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { login, getToken, getPatientId, clearToken, googleLoginUrl, savePatientId } from '@/lib/api/auth'
import { getMyProfile } from '@/lib/api/patients'
import { USE_MOCK } from '@/lib/config'
import PatientHeader from '@/components/patient/PatientHeader'

export default function PatientSignInPage() {
  const router = useRouter()
  const params = useSearchParams()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (params.get('error') === 'unlinked') {
      // Came back from OAuth with a Google account not linked to a patient —
      // clear the token so the guard doesn't redirect back to check-in
      clearToken()
      setError("This Google account isn't linked to a patient profile yet. Try signing in with your email, or contact your physical therapist.")
      return
    }
    // Only auto-redirect if BOTH token and patient_id are present — otherwise
    // PatientGuard will bounce us right back here and we'll loop.
    if (getToken() && getPatientId()) {
      router.replace('/patient/check-in')
    } else if (getToken() && !getPatientId()) {
      // Stale token without a linked patient profile — clear it so the user
      // can sign in cleanly.
      clearToken()
    }
  }, [router, params])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await login(email, password)

      // Resolve patient_id from the logged-in user's linked patient
      if (USE_MOCK) {
        savePatientId('P001')
      } else {
        const profile = await getMyProfile()
        if (!profile) {
          setError("Your account isn't linked to a patient profile yet. Contact your physical therapist.")
          setBusy(false)
          return
        }
        savePatientId(profile.id)
      }

      router.replace('/patient/check-in')
    } catch (exc) {
      setError((exc as Error).message)
      setBusy(false)
    }
  }

  const handleGoogle = () => {
    window.location.href = googleLoginUrl()
  }

  return (
    <div className="flex flex-col flex-1">
      <PatientHeader />

      <div className="flex flex-col flex-1 justify-center gap-6">
        <div>
          <h1 className="text-2xl font-bold text-[#1a1208]">Welcome back</h1>
          <p className="text-[#1a1208]/60 mt-1 text-sm">Sign in to check in to your session</p>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            <label className="text-xs font-semibold text-[#1a1208]/50 uppercase tracking-wider">
              Email
            </label>
            <input
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="rounded-xl border border-[#1a1208]/15 bg-white/70 px-4 py-3 text-[#1a1208] placeholder:text-[#1a1208]/30 focus:outline-none focus:ring-2 focus:ring-[#e8622c]/40"
              placeholder="you@example.com"
            />
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-xs font-semibold text-[#1a1208]/50 uppercase tracking-wider">
              Password
            </label>
            <input
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="rounded-xl border border-[#1a1208]/15 bg-white/70 px-4 py-3 text-[#1a1208] placeholder:text-[#1a1208]/30 focus:outline-none focus:ring-2 focus:ring-[#e8622c]/40"
              placeholder="••••••••"
            />
          </div>

          {error && (
            <p className="text-sm text-red-600 break-words">{error}</p>
          )}

          <button
            type="submit"
            disabled={busy}
            className="mt-1 rounded-xl bg-[#e8622c] hover:bg-[#d4561f] disabled:opacity-50 text-white text-base font-semibold py-3.5 transition-colors"
          >
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <div className="flex items-center gap-3">
          <div className="flex-1 h-px bg-[#1a1208]/10" />
          <span className="text-xs text-[#1a1208]/40">or</span>
          <div className="flex-1 h-px bg-[#1a1208]/10" />
        </div>

        <button
          onClick={handleGoogle}
          className="rounded-xl border border-[#1a1208]/15 bg-white/70 hover:bg-white/90 text-[#1a1208] text-base font-medium py-3.5 flex items-center justify-center gap-2 transition-colors"
        >
          <svg className="w-5 h-5" viewBox="0 0 24 24">
            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
            <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
          </svg>
          Continue with Google
        </button>
      </div>
    </div>
  )
}
