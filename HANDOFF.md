# ARES — CV + Backend + Frontend Handoff

This document captures the work done in the last session so the next person (and
their Claude) can pick up cleanly. It covers what changed, why, where the new
pieces live, how to run it, and what's left.

The original implementation plan is at
`~/.claude/plans/ok-now-that-we-vivid-axolotl.md` (or in your shell history).
Read this doc first; consult the plan only if you want the original framing.

---

## Big picture

Before this session ARES had:
- A CV server that used **YOLO11 + IoU-only tracking** and **InsightFace `buffalo_l`** for identity. It accepted RTSP/WebRTC, ran MediaPipe pose per crop, emitted per-frame data over a single WebSocket. Auto-enrolled new patients from face video.
- A backend with patient CRUD, auth, AI chat — no concept of "is this patient currently in the gym right now."
- A frontend Room Monitor view that displayed entirely **simulated** patient bboxes (`useSimulatedUpdates` ticking random numbers over a hardcoded grid).

After this session:

- **No face recognition anywhere.** Identity is bound via an **ArUco marker** the patient holds up on their phone. CV is identity-stateless; binding lives only in-memory while a session is active.
- **YOLO11 + BoT-SORT with CLIP-ReID embeddings.** Real multi-object tracking with appearance-based re-ID through short occlusions.
- **Per-stream model dispatch.** The `security` worker runs YOLO + ArUco only (no pose) so it stays cheap at ~30 FPS. The `detail` worker runs YOLO + pose for coaching.
- **GymSession lifecycle on the backend.** New table + routes for `CHECKING_IN → ACTIVE → LOST → LEFT`. Backend subscribes to CV's identity events over WebSocket and mirrors them into SQLite.
- **Real-time admin frontend.** Room Monitor captures the laptop webcam, broadcasts to CV via WebRTC, and overlays real bboxes + patient_id labels from CV's WebSocket feed.
- **Patient web pages.** Three mobile-shaped screens (`/patient/check-in`, `/patient/marker`, `/patient/lost`) that drive the lifecycle without admin auth. Hardcoded to a single patient (`P001`) for the demo.

The full implementation plan that this work followed is in
`~/.claude/plans/ok-now-that-we-vivid-axolotl.md`. The "Build `CV/pose_rtm.py`
(RTMPose for the detail stream)" item from that plan is still **pending**.

---

## Architecture today

Three services. All on localhost in dev; the long-term plan is CV on a Brev GPU
box with Cloudflare Tunnel, backend on Vercel.

```
┌──────────────────────┐         ┌──────────────────────┐         ┌──────────────────────┐
│  Frontend            │         │  Backend             │         │  CV                  │
│  Next.js :3000       │         │  FastAPI :8000       │         │  FastAPI :8001       │
│                      │  HTTP   │                      │  HTTP   │                      │
│  /dashboard          │ ──────▶ │  /gym/check_in       │ ──────▶ │  /live/check_in      │
│  (Room Monitor)      │         │  /gym/{id}/leave     │         │  /live/checkout      │
│  /patient/*          │         │  /gym/{id}/still_here│         │  /live/marker.png    │
│                      │         │  /gym                │         │  /webrtc/offer       │
│                      │ ◀────── │                      │ ◀────── │                      │
│                      │  WS     │                      │   WS    │  /live/events        │
│                      │ ──────▶ │                      │ ──────▶ │  /live/ws            │
│                      │         │                      │         │                      │
│  Captures webcam,    │         │  SQLite gym_sessions │         │  YOLO11+BoT-SORT     │
│  WebRTC → CV         │         │  + WS subscriber to  │         │  ArUco marker watch  │
│  Polls /gym for      │         │  CV identity events  │         │  Per-stream workers  │
│  state              │         │                      │         │                      │
└──────────────────────┘         └──────────────────────┘         └──────────────────────┘
```

### CV (port 8001)
- Long-lived `uvicorn`. Owns models, the live `LiveSession`, WebRTC peer
  connections, and the in-memory `IdentityRegistry`.
- Stateless about patients — no on-disk patient DB. The backend tells it which
  patient to expect; CV reports bind / lost / found events back.

### Backend (port 8000)
- FastAPI + SQLite. Owns `users`, `patients`, `gym_sessions`, etc.
- Subscribes to CV's `/live/events` WebSocket as a background task at startup,
  reconnects with backoff.
- Translates CV events into `gym_sessions.state` transitions.

### Frontend (port 3000)
- Next.js 16 app router. Two surfaces:
  - **Admin** (`/dashboard` → Room Monitor): laptop webcam captures, broadcasts
    to CV via WebRTC, overlays real bboxes from CV's `/live/ws`. Side panel polls
    `/gym` to show check-in state.
  - **Patient** (`/patient/*`): mobile-shaped screens for the lifecycle. No
    admin layout, no auth.

---

## Identity model

There's no face recognition. The flow:

1. Patient opens `/patient/check-in` and taps a button.
2. Frontend POSTs `/gym/check_in {patient_id}` to backend.
3. Backend creates a `gym_sessions` row (`state = CHECKING_IN`) and POSTs
   `/live/check_in {patient_id}` to CV.
4. CV's `IdentityRegistry.expect_check_in(patient_id)` adds the patient to a
   "watching" set.
5. Patient is redirected to `/patient/marker?session_id=N`. The page renders a
   fullscreen ArUco marker (PNG from `GET /live/marker.png`).
6. Patient holds the phone screen up to the gym camera.
7. CV's `security` worker runs `cv2.aruco.detectMarkers` on each frame. When
   `marker_id == 0` lands inside a YOLO bbox, the registry binds
   `patient_id ↔ track_id` and emits `patient_checked_in` on `/live/events`.
8. Backend's WS subscriber flips state to `ACTIVE`.
9. Frontend (polling `/gym/{id}` every second) sees state change.

**Why ArUco markers and not a real mobile ID:**
- No biometrics, no face recognition.
- Phone screens always work — no extra hardware.
- The marker is a logical ID, not a biological one — easy to revoke.

**Single hardcoded marker (`CHECK_IN_MARKER_ID = 0`)** for now. The dictionary
is `DICT_4X4_50` (50 unique IDs available), so adding a marker pool for
multiple simultaneous patients is a small change.

**Lost-track flow:**
- BoT-SORT keeps tracks alive for `track_buffer = 30` frames (~1s at 30 FPS)
  using Kalman prediction + appearance ReID.
- After BoT-SORT gives up, the `IdentityRegistry`'s watcher thread waits an
  additional `LOST_TIMEOUT_S = 5s` before emitting `patient_lost`.
- Total budget before a "lost" event: ~7 seconds of being out of frame.
- Patient app sees `state = LOST` and shows the lost prompt ("I'm still here" /
  "I'm leaving").

---

## File map (only files we changed or created)

### CV (`/CV`)
- **`bounding_box.py`** — Swapped tracker to BoT-SORT. `extract_bounding_boxes`
  now takes an optional `tracker` kwarg defaulting to the project-local
  `botsort.yaml`.
- **`botsort.yaml`** (new) — BoT-SORT config with `with_reid: True`,
  `track_buffer: 30`, `track_high_thresh: 0.6`, `new_track_thresh: 0.7`. Tuned
  to avoid spurious tracks while still surviving short occlusions.
- **`identity.py`** (new) — `IdentityRegistry`. ArUco detection (single
  hardcoded marker ID 0), `track_id ↔ patient_id` binding, lost-track watcher
  thread, event emitter (`patient_checked_in` / `patient_lost` /
  `patient_found`). Detector params tuned for phone-screen LCDs but tight
  enough to reject wood-grain false positives. Marker PNG includes a 200px
  white quiet-zone border (mandatory for ArUco detection).
- **`live_session.py`** — Per-stream dispatch: the `security` worker runs
  YOLO + ArUco, no pose. The `detail` worker runs YOLO + pose. `LiveFrame`
  now carries `patient_id`, `frame_w`, `frame_h`. New `replace_stream_source`
  method for hot-swapping a stream when the phone re-broadcasts. Per-frame
  exception handler logs and continues instead of crashing the worker.
- **`api.py`** — New endpoints: `POST /live/check_in`, `POST /live/checkout`,
  `GET /live/marker.png`, `WS /live/events`. Existing `/live/ws` rewritten to
  block on `_session_ready` and survive `/live/stop` → `/live/start` cycles.
  CORS middleware added (allows `*` for now). Viewer JS shows `patient_id`
  next to `track_id`.
- **`pipeline.py`** — Removed: `scan_persons`, `register_patient`,
  `get_patient`, `list_patients`, `assign_exercises`, `track_all_patients`,
  `track_and_log_patient`, `_session_track_map`, `_face()`, `PersonResult`,
  `PatientResult`, `PatientFrame`. Patient CRUD now lives entirely on the
  backend.
- **`face_id.py`** — **Deleted**. Along with the on-disk patient face DB.
- **`demo.py`** — Rewritten. Enumerates track IDs from a video and runs the
  classification/keypoint pipeline; no more `scan_persons` flow.

### Backend (`/backend`)
- **`app/core/config.py`** — Added `CV_INTERNAL_BASE` env var (defaults to
  `http://localhost:8001`). Use this for backend→CV server calls instead of
  `CV_API_BASE` so we don't bounce through ngrok for internal traffic.
- **`app/db/database.py`** — Added `gym_sessions` table with
  `state ∈ {CHECKING_IN, ACTIVE, LOST, LEFT}`, `started_at`, `ended_at`,
  `last_event`. Indexed by patient_id.
- **`app/routers/gym.py`** (new) — Five endpoints:
  - `POST /gym/check_in` — idempotent. Creates a session if none exists,
    re-arms CV's watch if one does. Returns marker URL.
  - `POST /gym/{id}/still_here` — re-arms CV after lost prompt.
  - `POST /gym/{id}/leave` — ends session, tells CV to checkout.
  - `GET /gym/{id}` — single session state.
  - `GET /gym` — list all non-LEFT sessions.
  - Background task `cv_event_subscriber()` runs from `main.py`'s lifespan,
    holds a persistent WebSocket to `/live/events`, reconnects with backoff.
  - All routes **unauthenticated** for now (TODO comment in the file) so the
    patient web flow can hit them without a JWT.
- **`app/main.py`** — Wired in the new router + the lifespan task.
- **`requirements.txt`** — Added `websockets>=12.0`.
- **`.env`** — Two new vars (in `.env.example`-style form):
  ```
  CV_API_BASE=https://<your-ngrok-host>             # phone-facing
  CV_INTERNAL_BASE=http://localhost:8001            # backend→CV
  ```

### Frontend (`/frontend`)
- **`src/lib/config.ts`** — Added `CV_BASE` (used for `/webrtc/offer` and
  `/live/marker.png` — needs to be reachable from phones, so ngrok) and
  `CV_WS_BASE` (used for the long-lived `/live/ws` from the admin browser,
  defaults to `localhost:8001` because ngrok free tier sometimes blocks
  browser-origin WebSockets).
- **`src/lib/patient.ts`** (new) — `DEMO_PATIENT_ID = 'P001'`.
- **`src/hooks/useLiveSecurityStream.ts`** (new) — Owns:
  - WebRTC peer connection that captures the laptop webcam, calls
    `/live/start_webrtc` (idempotent on 409), then POSTs SDP offer to CV.
  - Reconnecting `/live/ws` subscription that buffers detections by
    `frame_idx` and emits one `LiveFrame` per source frame.
  - Tracks the source frame size from `frame_w`/`frame_h` on every detection
    (the local `<video>` element's `videoWidth` is the **camera's** capture
    res, not what aiortc actually downsamples to — they differ).
- **`src/components/room-monitor/LiveCameraCanvas.tsx`** (new) — `<video>` +
  `<canvas>` overlay. Computes the visible-video rect inside the letterboxed
  `object-contain` element and draws bboxes in that coordinate space. Click
  selects the patient whose bbox the click is inside.
- **`src/hooks/useGymSessions.ts`** (new) — Polls `GET /gym` every 1.5s for
  the admin side panel.
- **`src/hooks/useGymSession.ts`** (new) — Polls `GET /gym/{id}` every 1s for
  the patient pages.
- **`src/components/room-monitor/LiveInspector.tsx`** (new) — Replaces the
  mock-driven `PatientInspector` for the Room Monitor. Shows Start/Stop
  broadcast button + the polled gym sessions with state badges.
- **`src/components/views/RoomMonitorView.tsx`** — Rewritten to use the above.
  No more `useSimulatedUpdates`. Other dashboard views still use the mock.
- **`src/app/patient/layout.tsx`** (new) — Mobile-shaped layout (no sidebar).
- **`src/app/patient/check-in/page.tsx`** (new) — Single "Check in" button.
  On mount, redirects to the marker page if a P001 session already exists.
- **`src/app/patient/marker/page.tsx`** (new) — Fullscreen marker PNG, state
  banner. Re-arms `/gym/check_in` on mount (insurance against CV restarts
  wiping its in-memory registry). Polls `/gym/{id}` and redirects to
  `/patient/lost` on `state = LOST`.
- **`src/app/patient/lost/page.tsx`** (new) — Two big buttons ("I'm still
  here" → `/still_here`, "I'm leaving" → `/leave`).

---

## Running the system

Three terminals.

```fish
# 1. CV
cd ~/Developer/git_repos/solstice/ARES/CV
uvicorn api:app --host 0.0.0.0 --port 8001

# 2. Backend
cd ~/Developer/git_repos/solstice/ARES/backend
pip install -r requirements.txt    # picks up websockets if not installed
uvicorn app.main:app --reload --port 8000

# 3. Frontend
cd ~/Developer/git_repos/solstice/ARES/frontend
npm run dev                        # http://localhost:3000
```

`.env` files you'll need:

- `backend/.env`:
  ```
  CV_API_BASE=https://<your-ngrok-host>
  CV_INTERNAL_BASE=http://localhost:8001
  # ...plus existing SECRET_KEY etc.
  ```
- `frontend/.env.local`:
  ```
  NEXT_PUBLIC_API_BASE=http://localhost:8000
  NEXT_PUBLIC_CV_BASE=https://<your-ngrok-host>      # for marker PNG + WebRTC
  NEXT_PUBLIC_CV_WS_BASE=http://localhost:8001       # for /live/ws (avoid ngrok)
  ```

### Why ngrok at all?

Mobile Safari requires HTTPS for `getUserMedia` and to render fullscreen images
from cross-origin domains. The Cloudflare Tunnel mentioned in the original plan
is preferred for prod (free, stable URL). For local dev, ngrok works:

```fish
ngrok http --domain=<your-reserved-domain> 8001
```

Phone-facing URLs (`/live/marker.png`, the WebRTC offer) go through ngrok.
Browser-side WS (`/live/ws`) goes directly to `localhost:8001`.

### End-to-end test (admin + patient)

1. Open the admin dashboard at `http://localhost:3000/dashboard` and switch to
   **Room Monitor**.
2. Click **Start broadcast**. Webcam preview appears, bboxes overlay on people.
3. In a second tab (or on your phone): `http://localhost:3000/patient/check-in`.
4. Tap **Check in** → you're routed to the marker page.
5. Hold the phone screen up to the camera (or open `/live/marker.png` on a
   second device).
6. Within ~1 second the marker page banner flips to "Checked in ✓" and the
   admin side panel shows P001 · Active.
7. Walk out of frame for 7s — marker page redirects to `/patient/lost`,
   admin side panel shows P001 · Lost.
8. Tap **I'm still here** → marker page again → walk back in → Active.
9. Tap **Leave gym** → session ends, redirected to check-in.

CV terminal during this should print, in order:

```
expect_check_in P001 — watching 1 patients total
aruco: marker 0 at (...) -> track 1
event: patient_checked_in patient=P001 track=1 → 1 listener(s)
...
event: patient_lost patient=P001 track=None → 1 listener(s)
...
event: patient_found patient=P001 track=2 → 1 listener(s)
```

---

## Known issues / gotchas

1. **CV's identity registry is in-memory.** A CV restart wipes it. The marker
   page re-calls `/gym/check_in` on mount specifically to handle this, but if
   you only use the admin dashboard you might see a stale `Checking in` badge
   after a CV restart. The fix is to re-arm via the patient page.

2. **Frontend Room Monitor doesn't mirror the camera preview.** Earlier we
   tried `scaleX(-1)` and it broke things; the current code leaves the preview
   as-is. If your camera produces mirrored output (some external cams do),
   bboxes will look flipped. Toggle the mirror via `style={{ transform: ... }}`
   on the `<video>` element if needed.

3. **BoT-SORT downloads CLIP-ReID weights on first use.** First frame after a
   fresh install can take 10–20s to process. Subsequent runs are instant.

4. **ngrok free tier** sometimes blocks browser-origin WebSockets. That's why
   `NEXT_PUBLIC_CV_WS_BASE` defaults to `localhost`. Don't point it at ngrok
   unless you've tested that path.

5. **Multiple patients.** Currently the system supports exactly one patient at
   a time (`CHECK_IN_MARKER_ID = 0` and `DEMO_PATIENT_ID = 'P001'` hardcoded).
   See "what's next" below.

6. **ArUco detector params.** Tuned to work on phone-screen LCDs while
   rejecting wood-grain ceilings. If you change rooms / lighting / cameras,
   tweak `polygonalApproxAccuracyRate` and the adaptive threshold window in
   `identity.py`.

7. **Patient routes are unauthenticated.** TODO marker is in `gym.py`. Need a
   patient-token scheme before this is real-usable.

---

## What's next (priority order)

These are in roughly the order they should be picked up:

1. **Multi-patient marker pool.** Promote `marker_id` from a constant to a
   per-session value in `gym_sessions`. Allocate from the unused IDs in
   `DICT_4X4_50` at check-in. Patient page renders whichever marker the
   backend handed back. (~1 hour.)

2. **Detail-stream RTMPose** (this is the one pending item from the plan).
   New `CV/pose_rtm.py` using `rtmlib` with `CUDAExecutionProvider`. Wire it
   into `live_session._run_stream` for `worker.name == DETAIL_STREAM`.
   Frontend needs a topology switch for COCO-17 vs MediaPipe-33 skeletons.
   Offline endpoints (`/extract_keypoints`, `/analyze_form`) keep MediaPipe
   for now — those are tightly coupled to `form_analysis.py`'s 33-point DTW.

3. **Patient mobile app.** The plan was always for `/patient/*` to be a
   temporary surface; a real mobile app should replace it. The web pages are
   designed to be a 1:1 reference for the mobile flow.

4. **GPU deployment to Brev.** The plan walks through Cloudflare Tunnel +
   `CV_API_BASE=https://cv.yourdomain.com`. Backend stays on Vercel; CV moves
   to the GPU box. The CV → backend event channel becomes HTTP webhooks
   instead of a WebSocket (Vercel serverless can't hold long connections).

5. **Real patient auth on `/gym/*` routes.** Add a patient-token scheme.

6. **ngrok → Cloudflare Tunnel for local dev.** Free, stable URL, no
   account-tier limits. Already in the plan.

7. **Polish:**
   - Push notification (vs polling) for `patient_lost`.
   - Bigger / printed ArUco markers for visibility from across a real gym.
   - Wider `track_buffer` once we've verified the demo works.

---

## Useful curl recipes

```fish
# Force-leave any active P001 session (useful when resetting)
set TOKEN dummy  # routes are currently unauth'd; replace if auth lands
curl -s http://localhost:8000/gym | python3 -m json.tool
# find the id, then:
curl -sX POST http://localhost:8000/gym/<id>/leave

# Test backend → CV directly
curl -sX POST http://localhost:8000/gym/check_in \
  -H 'content-type: application/json' \
  -d '{"patient_id":"P001"}'

# Test CV directly (skip backend)
curl -sX POST http://localhost:8001/live/check_in \
  -H 'content-type: application/json' \
  -d '{"patient_id":"P001"}'

# Reset CV's live session
curl -sX POST http://localhost:8001/live/stop
curl -sX POST http://localhost:8001/live/start_webrtc

# Tail CV identity events from the terminal
brew install websocat
websocat ws://localhost:8001/live/events
```

---

## Context for Claude

If you're a fresh Claude instance picking this up: the original plan is at
`~/.claude/plans/ok-now-that-we-vivid-axolotl.md`. It frames the *why* — gym
tracking, ArUco-instead-of-face-recognition, the per-stream model split, and
the deployment topology. Read that first if you want the design rationale.

The auto-memory under `~/.claude/projects/-Users-ashwin-Developer-git-repos-solstice-ARES/memory/`
has a project overview and "next steps" entries that may also be useful, but
parts of those predate this work — verify against the actual code before
relying on them.

Files most worth reading first, in order:
1. `CV/identity.py` — the heart of the new identity model.
2. `CV/live_session.py` — how streams + workers + identity all fit.
3. `backend/app/routers/gym.py` — the lifecycle state machine + CV event
   subscriber.
4. `frontend/src/hooks/useLiveSecurityStream.ts` — how the admin frontend
   captures + streams + listens.
5. `frontend/src/app/patient/` — the three lifecycle screens.

Good luck.
