'use client'
import SectionLabel from '@/components/shared/SectionLabel'
import AIAssistantPanel from '@/components/ai-assistant/AIAssistantPanel'

export default function AIAssistantView() {
  return (
    <div className="p-8 max-w-7xl mx-auto">
      <div className="mb-8">
        <SectionLabel>AI Assistant</SectionLabel>
        <h1 className="text-2xl font-bold text-text-primary">Clinical Intelligence</h1>
        <p className="text-text-muted mt-1">Ask questions about patients, sessions, alerts, and movement data</p>
      </div>
      <AIAssistantPanel />
    </div>
  )
}
