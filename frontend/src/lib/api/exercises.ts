import { USE_MOCK } from '@/lib/config'
import { MAYA_SQUAT_METRICS } from '@/data/exercises'
import type { ExerciseMetric } from '@/types'

export async function getExerciseMetrics(_patientId: string, _exerciseId: string): Promise<ExerciseMetric[]> {
  if (USE_MOCK) return MAYA_SQUAT_METRICS
  const res = await fetch(`${process.env.NEXT_PUBLIC_API_BASE}/patients/${_patientId}/exercises/${_exerciseId}/metrics`)
  return res.json()
}
