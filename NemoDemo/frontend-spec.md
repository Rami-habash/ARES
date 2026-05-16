# Solstice — AI Rehab Room Coach Dashboard
## Implementation Plan

---

## Context

Greenfield hackathon frontend project. No existing codebase. Goal: a visually polished, demo-ready command-center dashboard for a physical therapy / rehab room, inspired by Tribune's Devpost UI style (dark navy sidebar, cream workspace, editorial typography, diff-style cards) but built for healthcare monitoring. All data is mocked; no backend required.

---

## Tech Stack

- **Framework**: Next.js 14 (App Router)
- **Language**: TypeScript
- **Styling**: Tailwind CSS (custom config with Solstice palette)
- **Icons**: `lucide-react`
- **Animations**: `framer-motion`
- **UI Primitives**: `@radix-ui/react-dialog`, `@radix-ui/react-tabs`, `@radix-ui/react-select` (shadcn-style, installed manually)
- **Charts**: SVG/CSS-only (no chart lib dependency)
- **No external assets required**

---

## Setup Commands

```bash
mkdir -p frontend
cd frontend
npx create-next-app@latest . --typescript --tailwind --app --src-dir --import-alias "@/*"
npm install lucide-react framer-motion @radix-ui/react-dialog @radix-ui/react-tabs @radix-ui/react-select clsx
```

All frontend code lives exclusively under `frontend/`. The monorepo root is left clean for future `backend/`, `agents/`, `infra/`, etc. sibling directories.

---

## Color Palette (tailwind.config.ts additions)

```ts
colors: {
  sidebar: '#0f1623',       // dark navy
  workspace: '#f7f4ef',     // cream
  card: '#ffffff',
  border: '#e2e8f0',
  'text-primary': '#1e293b',
  'text-muted': '#64748b',
  'accent-green': '#16a34a',
  'accent-amber': '#d97706',
  'accent-red': '#dc2626',
  'accent-blue': '#2563eb',
  'pill-stable': '#dcfce7',
  'pill-review': '#fef9c3',
  'pill-risk': '#fee2e2',
  'diff-good': '#f0fdf4',
  'diff-bad': '#fff1f2',
}
```

---

## Repository Layout

```
/ (monorepo root)
├── frontend/               ← ALL frontend code lives here
│   ├── package.json
│   ├── next.config.ts
│   ├── tailwind.config.ts
│   └── src/
│       ├── app/
│       ├── components/
│       ├── lib/            ← API layer (swap mock → real with no component changes)
│       ├── data/           ← mock data (deleted when backend is live)
│       ├── types/
│       └── hooks/
├── backend/                ← future: FastAPI / Node service
├── agents/                 ← future: pose analysis agent, coaching agent
└── infra/                  ← future: docker-compose, k8s, etc.
```

## Frontend File Structure (`frontend/src/`)

```
src/
├── app/
│   ├── layout.tsx              # Root layout, loads fonts
│   ├── page.tsx                # Renders <AppShell />
│   └── globals.css             # Tailwind base + custom scrollbar
├── components/
│   ├── layout/
│   │   ├── AppShell.tsx        # Navigation state, view switcher
│   │   └── Sidebar.tsx         # Dark nav, icons, active state
│   ├── shared/
│   │   ├── StatusPill.tsx      # Stable / Needs Review / At Risk
│   │   ├── EvidenceChip.tsx    # Timestamp + label chip
│   │   ├── SectionLabel.tsx    # Uppercase small label
│   │   └── LiveDot.tsx         # Pulsing green dot
│   ├── views/
│   │   ├── DashboardView.tsx
│   │   ├── RoomMonitorView.tsx
│   │   ├── PatientsView.tsx
│   │   ├── ExerciseDetailView.tsx
│   │   ├── AlertsView.tsx
│   │   ├── ReportsView.tsx
│   │   ├── AIAssistantView.tsx
│   │   └── SettingsView.tsx
│   ├── dashboard/
│   │   ├── StatCard.tsx
│   │   ├── PatientCard.tsx
│   │   ├── EventTimeline.tsx
│   │   └── FacilityRiskPanel.tsx
│   ├── room-monitor/
│   │   ├── CameraCanvas.tsx    # CSS-based fake camera feed
│   │   ├── BoundingBox.tsx     # Patient overlay box
│   │   └── PatientInspector.tsx
│   ├── exercise/
│   │   ├── PoseVideoMock.tsx   # SVG skeleton + CSS video frame
│   │   ├── MovementDiffTable.tsx
│   │   └── CoachingPanel.tsx
│   ├── alerts/
│   │   ├── AlertCard.tsx
│   │   └── TriageSummary.tsx
│   ├── reports/
│   │   └── ReportPreview.tsx
│   ├── ai-assistant/
│   │   └── AIAssistantPanel.tsx
│   └── settings/
│       └── DemoControls.tsx
├── lib/
│   ├── api/
│   │   ├── patients.ts         # getPatients(), getPatient(id), updatePatientStatus()
│   │   ├── alerts.ts           # getAlerts(), dismissAlert(), escalateAlert()
│   │   ├── exercises.ts        # getExerciseMetrics(patientId, exerciseId)
│   │   ├── reports.ts          # generateReport(patientId, sessionId)
│   │   └── ai.ts               # streamAIResponse(query) → AsyncGenerator
│   └── config.ts               # API_BASE_URL (env var), feature flags
├── data/
│   ├── patients.ts             # mock data only — deleted when backend is live
│   ├── alerts.ts
│   ├── exercises.ts
│   └── events.ts
├── types/
│   └── index.ts
└── hooks/
    ├── useSimulatedUpdates.ts  # setInterval-based live ticker
    └── useDemoState.ts         # Global demo toggle state
```

---

## Types (`src/types/index.ts`)

```ts
export type PatientStatus = 'Stable' | 'Needs Review' | 'At Risk'
export type AlertSeverity = 'Critical' | 'Warning' | 'Info'
export type AlertStatus = 'Open' | 'Dismissed' | 'Escalated'
export type NavItem = 'dashboard' | 'room-monitor' | 'patients' | 'exercise' | 'alerts' | 'reports' | 'ai-assistant' | 'settings'

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

export interface SessionEvent {
  id: string
  time: string
  type: 'alert' | 'rep' | 'phase' | 'note'
  description: string
}
```

---

## Mock Data (`src/data/patients.ts`)

Four patients with full profiles:
- **Maya Patel** P-102, 62, Mat 2, Stable, Bodyweight Squat, formScore 76, Medium risk, adherence 82%
- **Jordan Lee** P-107, 45, Mat 4, Needs Review, Arm Raise, formScore 68, Medium risk, adherence 71%
- **Elena Garcia** P-089, 71, Gait Lane, At Risk, Assisted Walk, formScore 54, High risk, adherence 63%
- **Robert Chen** P-115, 58, Mat 1, Stable, Step-Up, formScore 88, Low risk, adherence 91%

Alerts data (`src/data/alerts.ts`): 6–8 alerts spanning all severities.

Exercise metrics (`src/data/exercises.ts`): Full diff rows for Maya's squat session.

---

## Component Implementation Details

### AppShell.tsx
- `useState<NavItem>('dashboard')` for active view
- `useState<string | null>(null)` for selected patient
- Passes `setActiveView`, `setSelectedPatient` as props down
- Renders `<Sidebar>` + main content area side by side
- Framer Motion `<AnimatePresence>` wraps view content for fade transitions

### Sidebar.tsx
- Fixed width `w-64`, full height, `bg-sidebar` color
- Top: Logo mark + "SOLSTICE" wordmark
- Nav items with lucide icons: LayoutDashboard, Monitor, Users, Activity, AlertTriangle, FileText, MessageSquare, Settings
- Active item: `bg-white/10 rounded-lg`
- "Room Monitor" has `<LiveDot />` pulsing green beside it
- Bottom: Building2 icon + "Switch Facility" in muted text

### DashboardView.tsx
- `REHAB COMMAND CENTER` label (uppercase, small, slate-500)
- H1: "Solstice Rehab Room"
- 5 StatCards in a grid: Patients Monitored (4), Active Sessions (3), Open Alerts (5), Avg Form Score (72.5), Exercises Completed (24)
- StatCards use `useSimulatedUpdates` to tick numbers slightly
- Below: 2-col layout — PatientCards list (left) + FacilityRiskPanel (right)
- Bottom: EventTimeline (last 8 events, most recent first)

### PatientCard.tsx
- White card, subtle shadow, rounded-xl
- Name + ID badge, zone label, status pill
- Progress bar for tracking confidence
- Risk score badge (colored)
- Current exercise with lucide `Dumbbell` icon
- Last event in muted text
- "Open Detail" button → `setActiveView('exercise')` + `setSelectedPatient(id)`

### RoomMonitorView.tsx
- Top: "ROOM MONITOR A" label, camera name, model badges
- Left 2/3: `<CameraCanvas>` — dark `#1a2333` bg, grid lines (CSS), subtle vignette
- Four `<BoundingBox>` absolutely positioned over canvas
- Right 1/3: `<PatientInspector>` — shows selected patient or "Click patient to inspect"
- Bottom strip: scrolling live event feed + model badges (MediaPipe, ByteTrack)

### CameraCanvas.tsx
- `relative` container, dark background, perspective grid lines via CSS
- Subtle "ROOM A — WIDE" watermark bottom-right
- Grid squares represent floor tiles
- `<BoundingBox>` positioned with top/left % values per patient

### BoundingBox.tsx
- Colored border box (green=stable, amber=review, red=at-risk)
- Top label bar: patient name + ID
- Bottom bar: exercise name + confidence%
- Pulsing outline animation via Framer Motion when selected
- Click handler to select patient

### PoseVideoMock.tsx (ExerciseDetail)
- SVG skeleton on dark background (17 landmark dots + connecting lines)
- Landmarks: nose, shoulders, elbows, wrists, hips, knees, ankles
- Animate subtle jitter on landmarks via Framer Motion to look "live"
- Overlay: rep counter, current phase badge, confidence score
- Skeleton lines use stroke colors matching status (green/amber/red per joint)

### MovementDiffTable.tsx
- Table-like card, each row = one metric
- Row bg: `diff-good` (muted green) or `diff-bad` (muted red)
- Columns: Metric | Reference | Observed | Status chip | Feedback
- Reference column: neutral
- Observed column: bold if deviation
- Status chip: small rounded pill

### AIAssistantPanel.tsx
- Page label + search/chat input (full-width, prominent)
- Suggested question chips below input
- On submit: fake streaming response with 4 "reasoning step" lines appearing sequentially (setTimeout stagger)
- Answer card with bold response text + EvidenceChips at bottom
- EvidenceChips: clickable-looking chips with session ID, alert ID, timestamp

### ReportPreview.tsx
- Clinical document aesthetic: clean, lots of whitespace, serif-inspired headings
- Header: patient name, session date, clinician placeholder
- Sections: Summary / Exercises Performed / Form Findings / Safety Events / AI Summary
- Each section uses `<SectionLabel>` + body text
- Evidence timeline at bottom (same EventTimeline component)
- Disclaimer box: "Demo note: This report is a movement-monitoring summary and does not replace clinical judgment."
- Action buttons: Download PDF (triggers browser print dialog), Copy summary (clipboard API), Mark Reviewed

### AlertsView.tsx
- Two-column: alert queue (left 2/3) + TriageSummary panel (right 1/3)
- Filter tabs: All / Critical / Warning / Info (using `@radix-ui/react-tabs`)
- Each AlertCard: severity color bar on left, title, patient, description, metric badge, timestamp
- Action buttons: Dismiss (removes from list locally), Review Clip (shows fake modal), Escalate (changes status)
- TriageSummary: counts, highest-risk patient, recommended action

### DemoControls.tsx (Settings)
- Toggle switches for: Live Updates, Risk Event Generation, Skeleton Overlay
- Select for: Active Patient, Camera Room
- Button: Reset Mock Data
- Slider: Model Confidence (50–100%)
- State lifted to AppShell via context or props

---

---

## API Layer (`src/lib/api/`)

All components import from `lib/api/*`, never from `data/*` directly. The API functions currently return mock data but are shaped to match what a real REST or WebSocket backend would return.

### Pattern

```ts
// lib/config.ts
export const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK !== 'false'
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? 'http://localhost:8000'

// lib/api/patients.ts
import { USE_MOCK, API_BASE } from '@/lib/config'
import { MOCK_PATIENTS } from '@/data/patients'
import type { Patient } from '@/types'

export async function getPatients(): Promise<Patient[]> {
  if (USE_MOCK) return MOCK_PATIENTS
  const res = await fetch(`${API_BASE}/patients`)
  return res.json()
}

export async function getPatient(id: string): Promise<Patient | undefined> {
  if (USE_MOCK) return MOCK_PATIENTS.find(p => p.id === id)
  const res = await fetch(`${API_BASE}/patients/${id}`)
  return res.json()
}
```

### Plugging in a real backend

Set `NEXT_PUBLIC_USE_MOCK=false` and `NEXT_PUBLIC_API_BASE=https://api.solstice.health` in `.env.local`.  
No component code changes required — only `lib/api/*` files need updating.

### WebSocket / streaming readiness

- `lib/api/ai.ts` exports `streamAIResponse(query)` returning an `AsyncGenerator<string>`  
  → mock: yields fake chunks via `setTimeout`  
  → real: wraps a `ReadableStream` from the agent endpoint
- Live room monitor updates: `useSimulatedUpdates` hook will swap to a `WebSocket` or SSE connection when `USE_MOCK=false`
- Pose skeleton data will arrive via WebSocket frame per patient per frame when connected to a real pose backend

---

## Simulated Live Updates (`src/hooks/useSimulatedUpdates.ts`)

```ts
// useInterval hook fires every 2–4 seconds when enabled
// Randomly nudges: trackingConfidence ±2, formScore ±1, repCount +1
// Occasionally pushes a new event to EventTimeline
// Respects demo toggle (pauses when disabled)
```

---

## Animations

- **View transitions**: Framer Motion `<AnimatePresence>` + `initial={{ opacity: 0, y: 8 }}` + `animate={{ opacity: 1, y: 0 }}`
- **Live dot**: CSS `animate-pulse` 
- **BoundingBox selection**: `scale: [1, 1.02, 1]` pulse
- **AI streaming steps**: `staggerChildren: 0.4s` reveal
- **Alert card enter**: slide in from right
- **Skeleton landmarks**: subtle `y: [-1, 1, -1]` oscillation loop

---

## Verification Plan

1. Run `npm run dev` — confirm no TS errors, page loads
2. Click all 8 sidebar nav items — each view renders
3. Dashboard: confirm stat cards show mock data, patient cards render, event timeline populates
4. Room Monitor: click each bounding box, confirm inspector panel updates
5. "Open Detail" from any patient → navigates to Exercise Detail with correct patient
6. Exercise Detail: diff table shows red/green rows, pose skeleton animates
7. Alerts: dismiss an alert (removes from list), tab filters work
8. Reports: Download PDF triggers print dialog, "Mark Reviewed" toggles state
9. AI Assistant: type a question, see streaming steps then answer card
10. Settings: toggle "Live Updates" — confirm stat cards stop/start ticking
11. Check at 1280px and 1440px viewport widths — no layout overflow

---

## Implementation Order

1. Monorepo root scaffold — create `frontend/`, `backend/` (empty), `agents/` (empty), `README.md`
2. Next.js project inside `frontend/` + tailwind config + globals.css
3. `src/types/index.ts` — all shared types
4. `src/data/*` — mock data
5. `src/lib/api/*` — API layer functions (mock-backed, env-switchable)
6. `src/lib/config.ts` — `USE_MOCK`, `API_BASE` env vars
7. Shared components (StatusPill, EvidenceChip, SectionLabel, LiveDot)
8. AppShell + Sidebar (navigation shell working end-to-end)
9. DashboardView (sets visual tone)
10. ExerciseDetailView (most important demo page)
11. RoomMonitorView (camera canvas + inspector)
12. AlertsView
13. PatientsView
14. ReportsView
15. AIAssistantView
16. SettingsView / DemoControls
17. Wire up `useSimulatedUpdates` + `useDemoState`
18. Final polish: animations, spacing, typography pass
19. Add `.env.local.example` documenting `NEXT_PUBLIC_USE_MOCK` and `NEXT_PUBLIC_API_BASE`
