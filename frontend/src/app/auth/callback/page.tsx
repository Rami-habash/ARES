'use client'
import { useEffect } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { saveToken } from '@/lib/api/auth'

export default function AuthCallback() {
  const router = useRouter()
  const params = useSearchParams()

  useEffect(() => {
    const token = params.get('token')
    const role  = params.get('role')

    if (token && role) {
      saveToken(token, role)
      router.replace('/dashboard')
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
