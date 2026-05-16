'use client'
import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { usePatientAuth } from '@/hooks/usePatientAuth'

interface Props {
  children: (patientId: string, signOut: () => void) => React.ReactNode
}

export default function PatientGuard({ children }: Props) {
  const { token, patientId, ready, signOut } = usePatientAuth()
  const router = useRouter()

  useEffect(() => {
    if (!ready) return
    if (!token || !patientId) {
      router.replace('/patient/sign-in')
    }
  }, [ready, token, patientId, router])

  if (!ready || !token || !patientId) {
    return (
      <div className="flex flex-col flex-1 justify-center items-center">
        <span className="w-6 h-6 border-2 border-[#e8622c]/30 border-t-[#e8622c] rounded-full animate-spin" />
      </div>
    )
  }

  return <>{children(patientId, signOut)}</>
}
