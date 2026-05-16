'use client'
import { useState, useRef } from 'react'
import EvidenceChip from '@/components/shared/EvidenceChip'
import { streamAIResponse } from '@/lib/api/ai'

const SUGGESTED = [
  "What is causing Maya's form score drop?",
  'Which patient has the highest fall risk today?',
  "Summarize Elena Garcia's gait session",
  'Recommend intervention for knee valgus',
]

export default function AIAssistantPanel() {
  const [query, setQuery] = useState('')
  const [steps, setSteps] = useState<string[]>([])
  const [answer, setAnswer] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const submit = async (q: string) => {
    if (!q.trim() || loading) return
    setLoading(true)
    setSteps([])
    setAnswer(null)
    setQuery(q)

    for await (const chunk of streamAIResponse(q)) {
      if (chunk.type === 'step') {
        setSteps(prev => [...prev, chunk.content])
      } else {
        setAnswer(chunk.content)
      }
    }
    setLoading(false)
  }

  return (
    <div className="max-w-3xl mx-auto">
      <div className="mb-6">
        <input
          ref={inputRef}
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && submit(query)}
          placeholder="Ask about any patient, session, or alert..."
          className="w-full px-5 py-4 text-lg border-2 border-border rounded-xl focus:outline-none focus:border-accent-blue transition-colors bg-card shadow-sm"
        />
        <div className="flex gap-2 mt-3 flex-wrap">
          {SUGGESTED.map(s => (
            <button
              key={s}
              onClick={() => submit(s)}
              className="text-xs px-3 py-1.5 bg-slate-100 text-text-muted rounded-full hover:bg-slate-200 transition-colors"
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {(steps.length > 0 || answer) && (
        <div className="bg-card rounded-xl border border-border shadow-sm p-6">
          {steps.length > 0 && (
            <div className="space-y-2 mb-4">
              {steps.map((step, i) => (
                <div key={i} className="flex items-center gap-2 text-sm text-text-muted">
                  <div className="w-4 h-4 rounded-full bg-accent-blue/20 flex items-center justify-center flex-shrink-0">
                    <div className="w-1.5 h-1.5 rounded-full bg-accent-blue" />
                  </div>
                  {step}
                </div>
              ))}
              {loading && (
                <div className="flex items-center gap-2 text-sm text-text-muted">
                  <div className="w-4 h-4 rounded-full bg-slate-100 flex items-center justify-center animate-pulse flex-shrink-0">
                    <div className="w-1.5 h-1.5 rounded-full bg-slate-400" />
                  </div>
                  Thinking...
                </div>
              )}
            </div>
          )}

          {answer && (
            <div>
              <div className="border-t border-border pt-4 mb-4">
                <p className="text-text-primary leading-relaxed whitespace-pre-wrap">{answer}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <EvidenceChip label="Session P-102-2024-01-15" timestamp="10:32 AM" />
                <EvidenceChip label="ALT-003: Knee Valgus" timestamp="10:30 AM" />
                <EvidenceChip label="Exercise metrics: Squat" />
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
