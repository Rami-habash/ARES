'use client'
import { useEffect } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { saveToken, savePatientId } from '@/lib/api/auth'
import { getMyProfile } from '@/lib/api/patients'

export default function AuthCallback() {
  const router = useRouter()
  const params = useSearchParams()

  useEffect(() => {
    const token = params.get('token')
    const role  = params.get('role')

    if (token && role) {
      saveToken(token, role)
      if (role === 'patient') {
        // Resolve and persist the patient_id before redirecting
        getMyProfile().then((profile) => {
          if (profile) {
            savePatientId(profile.id)
            router.replace('/patient/check-in')
          } else {
            // Google account exists but isn't linked to a patient record yet
            router.replace('/patient/sign-in?error=unlinked')
          }
        }).catch(() => {
          router.replace('/patient/sign-in?error=unlinked')
        })
      } else {
        router.replace('/dashboard')
      }
    } else {
      router.replace('/')
    }
  }, [params, router])

  return (
    <div className="min-h-screen bg-[#f2ece0] flex items-center justify-center">
      <div className="flex items-center gap-3 text-[#1a1208]/50">
        <span className="w-5 h-5 border-2 border-[#1a1208]/20 border-t-[#1a1208]/60 rounded-full animate-spin" />
        Signing you in...
      </div>
    </div>
  )
}
