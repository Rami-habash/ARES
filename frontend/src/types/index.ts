export type PatientStatus = 'Stable' | 'Needs Review' | 'At Risk'
export type AlertSeverity = 'Critical' | 'Warning' | 'Info'
export type AlertStatus = 'Open' | 'Dismissed' | 'Escalated'
export type NavItem = 'dashboard' | 'room-monitor' | 'patients' | 'exercise' | 'alerts' | 'reports' | 'ai-assistant' | 'settings'

export interface SessionEvent {
  id: string
  time: string
  type: 'alert' | 'rep' | 'phase' | 'note'
  description: string
}

export interface Patient {
  id: string
  name: string
  age: number
  zone: string
  status: PatientStatus
  currentExercise: string
  assignedExercises: string[]
  rehabPlan: string
  formScore: number
  riskScore: 'Low' | 'Medium' | 'High'
  adherence: number
  trackingConfidence: number
  restrictions: string[]
  lastSession: string
  recentEvents: SessionEvent[]
}

export interface Alert {
  id: string
  severity: AlertSeverity
  patientId: string
  patientName: string
  title: string
  description: string
  timestamp: string
  metric: string
  status: AlertStatus
}

export interface ExerciseMetric {
  metric: string
  reference: string
  observed: string
  status: 'Good' | 'Mild issue' | 'Needs correction'
  feedback: string
}
