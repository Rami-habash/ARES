import { API_BASE, USE_MOCK } from '@/lib/config'
import { authHeaders } from '@/lib/api/auth'

const MOCK_STEPS = [
  'Retrieving patient session data...',
  'Analyzing movement patterns across last 3 sessions...',
  'Cross-referencing clinical protocols...',
  'Generating coaching recommendation...',
]

const MOCK_ANSWER = `Based on Maya Patel's session data, the primary concern is right knee valgus during the squat descent phase (8.2° vs. reference <5°). This pattern, combined with the trunk forward lean (13.5°), suggests limited ankle dorsiflexion mobility may be driving compensatory mechanics.

**Recommended interventions:**
1. Add ankle mobility drills pre-session (3×30s heel-elevated stretch)
2. Cue "drive knees out" during descent
3. Consider heel wedge for next 2 sessions to reduce dorsiflexion demand
4. Monitor right knee pain levels — flag if VAS >3`

export async function* streamAIResponse(
  query: string,
): AsyncGenerator<{ type: 'step' | 'answer'; content: string }> {
  if (USE_MOCK) {
    for (const step of MOCK_STEPS) {
      await new Promise(r => setTimeout(r, 600))
      yield { type: 'step', content: step }
    }
    await new Promise(r => setTimeout(r, 400))
    yield { type: 'answer', content: MOCK_ANSWER }
    return
  }

  // Real backend: SSE stream from /ai/chat
  const res = await fetch(`${API_BASE}/ai/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ query }),
  })

  if (!res.ok || !res.body) {
    yield { type: 'answer', content: 'Error contacting AI assistant.' }
    return
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''

    for (const line of lines) {
      if (!line.startsWith('data:')) continue
      const raw = line.slice(5).trim()
      if (raw === '[DONE]') return
      try {
        const parsed = JSON.parse(raw) as { type: 'step' | 'answer'; content: string }
        yield parsed
      } catch {
        // partial JSON chunk — continue
      }
    }
  }
}
