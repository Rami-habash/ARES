'use client'
import { useEffect, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { API_BASE } from '@/lib/config'
import { authHeaders } from '@/lib/api/auth'
import PatientGuard from '@/components/patient/PatientGuard'
import PatientHeader from '@/components/patient/PatientHeader'

function renderMarkdown(md: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = []
  let listBuffer: string[] = []

  const flushList = (key: string) => {
    if (listBuffer.length === 0) return
    nodes.push(
      <ul key={key} className="list-disc list-inside space-y-1 text-[#1a1208]/80 text-sm pl-1">
        {listBuffer.map((item, i) => <li key={i}>{item}</li>)}
      </ul>
    )
    listBuffer = []
  }

  md.split('\n').forEach((line, i) => {
    if (line.startsWith('## ')) {
      flushList(`list-pre-${i}`)
      nodes.push(
        <h2 key={i} className="text-lg font-bold text-[#1a1208] mt-4 mb-1">
          {line.slice(3)}
        </h2>
      )
    } else if (line.startsWith('### ')) {
      flushList(`list-pre-${i}`)
      nodes.push(
        <h3 key={i} className="text-sm font-semibold text-[#1a1208]/70 uppercase tracking-wider mt-4 mb-1">
          {line.slice(4)}
        </h3>
      )
    } else if (line.startsWith('- ') || line.match(/^\d+\.\s/)) {
      listBuffer.push(line.replace(/^-\s|^\d+\.\s/, ''))
    } else if (line.trim() === '') {
      flushList(`list-${i}`)
      nodes.push(<div key={i} className="h-2" />)
    } else {
      flushList(`list-pre-${i}`)
      nodes.push(
        <p key={i} className="text-sm text-[#1a1208]/80">{line}</p>
      )
    }
  })
  flushList('list-final')

  return nodes
}

function ReportContent({ patientId }: { patientId: string }) {
  const router = useRouter()
  const params = useSearchParams()
  const sessionId = params.get('session_id')

  const [status, setStatus] = useState<'loading' | 'done' | 'error'>('loading')
  const [report, setReport] = useState<string | null>(null)

  useEffect(() => {
    if (!sessionId) {
      setStatus('error')
      return
    }

    fetch(`${API_BASE}/gym/${sessionId}/report`, {
      method: 'POST',
      headers: authHeaders(),
    })
      .then(async (r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        const data = await r.json()
        setReport(data.report ?? '')
        setStatus('done')
      })
      .catch(() => setStatus('error'))
  }, [sessionId, patientId])

  return (
    <div className="flex flex-col flex-1">
      <PatientHeader />

      {status === 'loading' && (
        <div className="flex flex-col flex-1 justify-center items-center gap-4">
          <span className="w-8 h-8 border-2 border-[#e8622c]/30 border-t-[#e8622c] rounded-full animate-spin" />
          <p className="text-[#1a1208]/60 text-sm text-center">
            Generating your report…<br />This may take up to 30 seconds.
          </p>
        </div>
      )}

      {status === 'error' && (
        <div className="flex flex-col flex-1 justify-center items-center gap-6 text-center">
          <p className="text-[#1a1208]/60">
            Couldn&apos;t generate your report. Please ask your physical therapist.
          </p>
          <button
            onClick={() => router.replace('/patient/check-in')}
            className="rounded-xl bg-[#e8622c] hover:bg-[#d4561f] text-white text-base font-semibold px-8 py-3.5 transition-colors"
          >
            Done
          </button>
        </div>
      )}

      {status === 'done' && report !== null && (
        <div className="flex flex-col flex-1 gap-6">
          <div>
            <h1 className="text-xl font-bold text-[#1a1208]">Your Session Report</h1>
            <p className="text-xs text-[#1a1208]/40 mt-0.5">
              {new Date().toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })}
            </p>
          </div>

          <div className="flex-1 rounded-2xl bg-white/60 border border-[#1a1208]/10 p-5 overflow-y-auto">
            {renderMarkdown(report)}
          </div>

          <button
            onClick={() => router.replace('/patient/check-in')}
            className="rounded-xl bg-[#e8622c] hover:bg-[#d4561f] text-white text-base font-semibold py-3.5 transition-colors"
          >
            Done
          </button>
        </div>
      )}
    </div>
  )
}

export default function PatientReportPage() {
  return (
    <PatientGuard>
      {(patientId) => <ReportContent patientId={patientId} />}
    </PatientGuard>
  )
}
