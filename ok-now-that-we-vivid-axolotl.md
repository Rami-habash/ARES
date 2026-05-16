# CV optimization + GPU offload + robust gym tracking

## Context

We have something flowing end-to-end now (YOLO11 + MediaPipe per-crop + S3D embeddings, served from `CV/api.py` on :8001, with backend on :8000). Two problems are blocking real use:

1. **No GPU.** Inference runs on the laptop. We have a Brev GPU box but nothing is using it.
2. **Live tracking is too fragile for a gym.** YOLO `.track(persist=True)` uses pure IoU continuation — fine for one or two well-separated people, but in a clinic with multiple patients, partial occlusions, and people leaving/re-entering the frame, track IDs swap and identity is lost. Face ID only runs once at scan time, so once a track ID flips the patient is misidentified for the rest of the session.

Also worth resolving upfront: there is **no duplicate CV server today**. `backend/` (:8000) handles auth/patients/AI chat; `CV/api.py` (:8001) is the only CV server. The split is intentional. We keep it.

**Goal of this change:** move CV to the Brev GPU box, replace IoU-only tracking with appearance-based multi-object tracking, bind patient identity to track IDs without relying on face recognition, and split per-stream model usage so the wide "security" stream stays cheap while the close-up "detail" stream gets a heavier, higher-accuracy pose model for coaching.

## Decisions (user-confirmed)

- Keep backend + CV split. CV moves to Brev; backend on laptop calls `CV_API_BASE=https://<brev-host>:8001`.
- Target: robust re-ID in a crowded gym, ~30 FPS live loop.
- Identity: **ArUco marker on patient phone is the only identity mechanism.** No facial recognition, anywhere — `face_id.py` and its pipeline calls are removed from the live path. BoT-SORT's appearance embeddings carry identity through normal occlusions; if the tracker loses a patient (track ID lost, no embedding match within timeout), the backend pushes a notification to that patient's mobile app asking them to hold the phone up for re-binding.
- The Roboflow blog's RF-DETR + SAM2 approach is rejected: blog itself reports 1–2 FPS on a T4. Wrong tool for real-time coaching. We borrow the *concept* of appearance embeddings (SigLIP-style), implemented via a real-time tracker.
- **Per-stream model split:** the wide *security* stream is for detection + tracking + identity only — no per-frame pose needed. The close-up *detail* stream is where the frontend wants accurate coaching, so it runs a stronger pose model (RTMPose) on every tracked crop. This keeps the security loop fast (~30 FPS) and concentrates GPU budget on the stream that actually needs pose quality.

## Approach

### Part 1 — Move CV to Brev

The smallest viable change: run the existing `CV/api.py` on Brev, point the backend at it.

- On Brev: install repo, install `requirements.txt` + CUDA `torch`, run `uvicorn api:app --host 0.0.0.0 --port 8001`. Open port 8001 (or tunnel through Brev's built-in HTTPS proxy).
- [CV/face_id.py](CV/face_id.py) and `pipeline._face()` / face-related calls in [CV/pipeline.py](CV/pipeline.py) (`scan_persons`, `register_patient`, face embedding DB) are no longer called from any live or scan endpoint. We can delete the modules outright or leave them dead — see "Cleanup" below.
- In [CV/video_embeder.py:30-36](CV/video_embeder.py#L30-L36): the CUDA branch already exists; just verify it picks up on Brev.
- In [CV/keypoint_extraction.py:17-35](CV/keypoint_extraction.py#L17-L35): MediaPipe Tasks stays CPU-bound. Used only by offline `analyze_form` / `extract_keypoints` calls now — see Part 4 for the live detail-stream replacement.
- Backend `.env`: set `CV_API_BASE=https://<brev-host>:8001`.
- WebRTC signalling: phones POST `/webrtc/offer` directly to Brev. Make sure Brev exposes the port with TLS — getUserMedia only works over HTTPS in mobile Safari.

No code changes required to make the architecture work — only config + a 1-line ONNX provider tweak. Verify the existing `os.environ["YOLO_DEVICE"]`-style auto-detect actually lands on `cuda` (it should via ultralytics).

### Part 2 — Replace IoU tracking with appearance-aware MOT

Swap [CV/bounding_box.py:14-23](CV/bounding_box.py#L14-L23) from default ultralytics tracker (`bytetrack.yaml`) to **BoT-SORT with ReID embeddings**, which ultralytics ships in-box (`botsort.yaml` with `with_reid: True`, `model: auto` uses CLIP-ReID weights). This gives us:

- Kalman-filter motion prediction (handles brief occlusions).
- Per-detection 512-d appearance embedding stored on each track.
- Embedding-based re-identification when a track is lost and re-enters.
- Runs at ~30 FPS for ~5 people on a single T4/A10 alongside YOLO11l.

Change is small: pass `tracker="botsort.yaml"` to `model.track(...)` and (optionally) ship a project-local `botsort.yaml` under [CV/](CV/) that sets `with_reid: True`, `proximity_thresh: 0.5`, `appearance_thresh: 0.25`.

Files touched:
- [CV/bounding_box.py](CV/bounding_box.py): add `tracker=` kwarg, expose the embedding on each box.
- [CV/live_session.py:123-159](CV/live_session.py#L123-L159): loop becomes **per-stream-typed**. The security worker stops calling `_landmarks_from_crop` entirely (it only needs bbox + track_id + ArUco for identity). The detail worker keeps pose extraction — see Part 4. We now trust track IDs across short occlusions.

### Part 3 — Identity binding via phone-displayed ArUco marker

ArUco is the sole identity mechanism. Phone GPS won't work indoors. UWB needs beacons. ArUco needs nothing except the phone the patient already has.

A patient's gym session has a clear lifecycle. We model it as an explicit state machine on the backend: `IDLE → CHECKING_IN → ACTIVE → LOST → (ACTIVE | LEFT)`.

**1. Check-in (`IDLE → CHECKING_IN → ACTIVE`)**

- Patient taps a "Check in" button on the mobile app.
- Backend creates a `GymSession` row (patient_id, started_at, marker_id) and tells CV `POST /live/expect_checkin {patient_id, marker_id}`. CV adds the marker_id to its "watching" set.
- App switches to a fullscreen ArUco marker view (rendered client-side from the marker_id; no need to fetch a PNG).
- Patient walks into camera view and holds the phone screen-out for 2–3 seconds.
- CV's security worker runs `cv2.aruco.detectMarkers` on each frame. When the watched marker_id is seen inside (or adjacent to) a YOLO bbox, CV binds `patient_id ↔ track_id`, emits `patient_checked_in` over the event channel, and BoT-SORT's appearance embedding then carries that identity even after the phone is pocketed.
- Backend flips session state to `ACTIVE` and pushes a confirmation to the app ("You're checked in — start your exercise"). App can dismiss the marker screen.

**2. Lost (`ACTIVE → LOST`)**

A patient is "lost" when their bound `track_id` has been gone for longer than `LOST_TIMEOUT_S` (proposal: 5s) without BoT-SORT recovering it via appearance match.

- CV emits `patient_lost {patient_id}` on the event channel.
- Backend flips session state to `LOST` and pushes a notification to that patient's mobile app:
  > "We lost track of you. Are you still here?"
  >
  >  - **I'm still here** — re-shows the marker for re-scan.
  >  - **I'm leaving** — ends the session.

**3a. Recovery (`LOST → ACTIVE`)**

- Patient taps "I'm still here." App re-renders the marker fullscreen.
- CV sees the marker again, re-binds `patient_id ↔ new track_id`, emits `patient_found`.
- Backend flips state back to `ACTIVE`, pushes confirmation, app dismisses marker.

**3b. Leaving (`LOST → LEFT`, or `ACTIVE → LEFT` if explicit)**

- Patient taps "I'm leaving" (either from the lost prompt, or from an always-available "Leave gym" button in the app while `ACTIVE`).
- Backend marks `GymSession.ended_at`, state `LEFT`.
- CV `POST /live/checkout {patient_id}`: drop the `patient_id ↔ track_id` binding, stop watching that marker_id.
- Transient session state is cleared per the data-retention rules below. Persisted exercise results (rep counts, form analyses) are kept; ephemeral live-tracking state (track-history embeddings, last-seen positions, the binding entry) is deleted.

**What "delete some info" means concretely**

Two retention tiers:
- **Persisted (survives checkout):** `GymSession` row with start/end timestamps; any `ExerciseAnalysis` records the backend wrote during the session (rep counts, form summaries, coach feedback).
- **Ephemeral (deleted on checkout):** CV-side per-session bindings in [CV/identity.py](CV/identity.py): the `track_id → patient_id` map entry, the patient's last-seen track timestamps, the watched-marker set entry. None of this needs to outlive the session; deleting it on `LEFT` keeps the next session clean.

Files touched:
- New: [CV/identity.py](CV/identity.py) — ArUco detection, `track_id → patient_id` session map, watched-marker set, lost-track timeout watcher, event emitter, checkout cleanup.
- New CV endpoints in [CV/api.py](CV/api.py):
  - `POST /live/expect_checkin {patient_id, marker_id}` — start watching a marker.
  - `POST /live/checkout {patient_id}` — drop binding + watched marker; clear ephemeral state.
  - Event channel (extend `/live/ws` or add `/live/events`) emits `patient_checked_in` / `patient_lost` / `patient_found` alongside per-frame data.
- New backend layer:
  - `GymSession` model + table (id, patient_id, started_at, ended_at, marker_id, state).
  - Routes: `POST /sessions/check_in`, `POST /sessions/{id}/still_here`, `POST /sessions/{id}/leave`. These call CV's `/live/expect_checkin` and `/live/checkout` and maintain state.
  - Subscriber to CV's event channel that translates `patient_lost` → push notification with the two-button prompt, and `patient_checked_in` / `patient_found` → confirmation pushes.
- New mobile app screens:
  - **Check-in** button → fullscreen marker (rendered client-side from marker_id).
  - **Active** view with a "Leave gym" action.
  - **Lost** prompt with "I'm still here" / "I'm leaving" actions.
- [CV/live_session.py](CV/live_session.py): on security frames, run aruco detection scoped to the watched-marker set; tag emitted `LiveFrame` with `patient_id` when known; maintain last-seen timestamps for the lost-track watcher.

**Marker assignment**

The 4×4 ArUco dictionary has 50 unique IDs, which is enough for a single gym at one time but not enough as a permanent per-patient identifier. So marker_id is **per-session**, assigned at check-in from a pool of currently-unused IDs in that gym. The mobile app renders whatever marker_id the backend hands back from `POST /sessions/check_in`. Permanent `patient_id` lives in the backend session row, not the marker.

### Part 4 — Detail-stream pose with RTMPose (in scope)

The detail stream is where the frontend wants accurate joint angles for coaching, so we upgrade it now instead of deferring. The security stream stays pose-free.

- Add **RTMPose-m** (COCO-17, ~26 MB) via the `rtmlib` Python wrapper, which loads ONNX with `CUDAExecutionProvider`. Avoids a full mmpose install.
- New module [CV/pose_rtm.py](CV/pose_rtm.py): singleton loader + `landmarks_from_crop(crop) -> list[Landmark]` matching the existing `Landmark` shape returned by [CV/pipeline.py](CV/pipeline.py), so downstream consumers (form_analysis, viewer JS) don't change.
- [CV/live_session.py](CV/live_session.py): in `_run_stream`, dispatch by `worker.name` — `"security"` skips pose, `"detail"` calls `pose_rtm.landmarks_from_crop` instead of `pipeline._landmarks_from_crop`.
- Frontend viewer's `POSE_CONNECTIONS` constant ([CV/api.py:341-348](CV/api.py#L341-L348)) is MediaPipe's 33-point topology; switch to COCO-17 topology when the detail stream is active. We can either gate this by `stream` in the JS or have the server emit the connection list alongside the first frame.
- Offline endpoints (`/extract_keypoints`, `/analyze_form`) keep using MediaPipe for now — those are video-file uploads, not the live loop, and the existing form-analysis DTW pipeline is keyed to the 33-point landmark layout. Migrating those is a separate cleanup.

This adds one model to the GPU but only runs it on the detail stream (one person of interest at a time, typically), so the cost is bounded. Expected: 8–12 ms per crop on a T4 → comfortably 30 FPS for the detail view alone.

## Critical files

- [CV/bounding_box.py](CV/bounding_box.py) — tracker swap (BoT-SORT + ReID).
- [CV/live_session.py](CV/live_session.py) — per-stream dispatch (security = bbox+aruco, detail = bbox+RTMPose), emit `patient_id` field.
- [CV/identity.py](CV/identity.py) — new, ArUco detection + session identity map.
- [CV/pose_rtm.py](CV/pose_rtm.py) — new, RTMPose-m loader + per-crop inference for the detail stream.
- [CV/api.py](CV/api.py) — surface `patient_id` over `/live/ws`; add `/patients/{id}/aruco.png` (or put in backend); make viewer JS aware of topology per stream.
- [CV/face_id.py](CV/face_id.py) — **delete** (or strand dead). Remove `pipeline._face()`, the face-DB on-disk store, and face calls from `scan_persons` / `register_patient` in [CV/pipeline.py](CV/pipeline.py). `register_patient` becomes "create patient row" (no face video); `scan_persons` becomes "report current track IDs and which are bound vs unbound."
- Backend `GymSession` model + check-in/leave/still-here routes; event subscriber to CV; push-notification wiring.
- Mobile app: check-in button → fullscreen marker; active view with "Leave gym"; lost prompt with two-button choice.
- Brev host config (no file in repo) — TLS, port, `CV_API_BASE` in backend `.env`.

## Functions/utilities to reuse

- `pipeline._bbox()`, `pipeline._pose()` in [CV/pipeline.py](CV/pipeline.py) — model singletons stay as-is.
- `pipeline._landmarks_from_crop()` — unchanged.
- `LiveFrame` TypedDict in [CV/live_session.py:31-37](CV/live_session.py#L31-L37) — extend with optional `patient_id`.
- Existing `frame_source.py` abstractions — unchanged.

## Verification

1. **GPU smoke test on Brev:**
   - `uvicorn api:app --host 0.0.0.0 --port 8001`
   - `curl https://<brev>/healthz` (add if missing) and `python -c "import torch; print(torch.cuda.is_available())"`.
   - Check `nvidia-smi` shows YOLO + S3D loaded on GPU after `/scan_persons` is called.

2. **Tracker upgrade:**
   - Record a 30s clip with 3 people crossing paths.
   - Run [CV/demo.py](CV/demo.py) before and after the swap.
   - Verify track IDs survive a person walking behind another. Old behavior: ID flips; new: ID persists.

3. **Full session lifecycle:**
   - Start `/live/start_webrtc` on Brev, broadcast from one phone as `security`.
   - On a second phone (patient), tap **Check in** → marker appears → walk into view → verify `patient_checked_in` event fires, app dismisses marker, viewer shows `patient_id` attached to the track.
   - Pocket the phone, walk around, walk behind another person. Verify `patient_id` stays glued to the right track via BoT-SORT embeddings.
   - Walk fully out of frame for >5s → verify `patient_lost` fires and the patient phone gets the "Are you still here?" prompt.
   - Tap **I'm still here** → marker re-renders → walk back in → verify `patient_found` and binding restored.
   - Repeat lost; this time tap **I'm leaving** → verify `GymSession.ended_at` is set, CV ephemeral state for that patient is cleared, persisted exercise records remain.
   - From a healthy `ACTIVE` state, tap **Leave gym** directly → same checkout behavior, no lost prompt.

4. **Detail-stream pose:**
   - Broadcast a second phone as `detail` close-up.
   - In the viewer, confirm the detail canvas draws a COCO-17 skeleton (not MediaPipe-33), keypoints look stable on knees/elbows.
   - Compare joint angles emitted by RTMPose vs. previous MediaPipe output on the same recorded clip; expect tighter, less jittery angles especially at occluded limbs.

5. **End-to-end latency:**
   - With the viewer open, measure glass-to-glass on a wall clock pointed at the broadcasting phone. Target: < 250ms.
   - `top` / `nvidia-smi` on Brev to confirm GPU is the active device, not CPU.
   - Security stream should hit ~30 FPS even with 4+ people in view; detail stream ~30 FPS with one person.
