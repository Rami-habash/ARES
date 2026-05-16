import type { ExerciseMetric } from '@/types'

export const MAYA_SQUAT_METRICS: ExerciseMetric[] = [
  {
    metric: 'Knee Flexion Depth',
    reference: '90°',
    observed: '87°',
    status: 'Good',
    feedback: 'Within acceptable range for post-TKR protocol',
  },
  {
    metric: 'Knee Valgus (L)',
    reference: '< 5°',
    observed: '4.1°',
    status: 'Good',
    feedback: 'Left knee tracking well',
  },
  {
    metric: 'Knee Valgus (R)',
    reference: '< 5°',
    observed: '8.2°',
    status: 'Needs correction',
    feedback: 'Medial collapse detected — cue hip external rotation',
  },
  {
    metric: 'Trunk Lean',
    reference: '< 10°',
    observed: '13.5°',
    status: 'Mild issue',
    feedback: 'Slight forward lean — may indicate ankle mobility limitation',
  },
  {
    metric: 'Hip Hinge Symmetry',
    reference: '> 90%',
    observed: '88%',
    status: 'Good',
    feedback: 'Bilateral loading near symmetric',
  },
  {
    metric: 'Descent Speed',
    reference: '2–3s',
    observed: '1.8s',
    status: 'Mild issue',
    feedback: 'Eccentric phase slightly fast — cue to slow down',
  },
  {
    metric: 'Ascent Symmetry',
    reference: '> 85%',
    observed: '91%',
    status: 'Good',
    feedback: 'Good push-through on both sides',
  },
]

export const EVENTS_TIMELINE = [
  { id: 'ev1', time: '11:02 AM', type: 'alert' as const, description: 'Elena Garcia: Fall risk threshold exceeded' },
  { id: 'ev2', time: '11:00 AM', type: 'alert' as const, description: 'Elena Garcia: Gait asymmetry detected' },
  { id: 'ev3', time: '10:45 AM', type: 'alert' as const, description: 'Jordan Lee: Scapular compensation pattern' },
  { id: 'ev4', time: '10:32 AM', type: 'rep' as const, description: 'Maya Patel: Completed rep 8/10' },
  { id: 'ev5', time: '10:30 AM', type: 'alert' as const, description: 'Maya Patel: Knee valgus detected' },
  { id: 'ev6', time: '10:15 AM', type: 'rep' as const, description: 'Robert Chen: Set 3 complete — excellent form' },
  { id: 'ev7', time: '10:12 AM', type: 'phase' as const, description: 'Robert Chen: Phase 3 strength & proprioception' },
  { id: 'ev8', time: '10:08 AM', type: 'note' as const, description: 'Robert Chen: Session started' },
]
