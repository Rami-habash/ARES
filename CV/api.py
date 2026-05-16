"""
ARES Movement Analysis API — FastAPI service.

All endpoints are thin wrappers over pipeline.py.
Models and reference embeddings are pre-loaded at startup.

Run:
  cd CV && uvicorn api:app --reload
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from contextlib import asynccontextmanager
from typing import Optional

import asyncio
import json

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from pydantic import BaseModel

import identity
import pipeline
from frame_source import WebRtcFrameSource
from live_session import LiveSession, LiveFrame


@asynccontextmanager
async def lifespan(app: FastAPI):
    pipeline._bbox()
    pipeline._pose()
    pipeline._s3d()
    pipeline.preload_references()
    yield


app = FastAPI(title="ARES Movement Analysis API", lifespan=lifespan)

# Allow the Next.js frontend (any origin in dev) to call /webrtc/offer,
# /live/check_in, /live/marker.png cross-origin. WebSockets don't go
# through CORS, so /live/ws + /live/events are unaffected.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _save_upload(upload: UploadFile) -> str:
    suffix = os.path.splitext(upload.filename or "")[1] or ".mp4"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    shutil.copyfileobj(upload.file, tmp)
    tmp.close()
    return tmp.name


# Patient CRUD lives on the backend (auth + SQLite). CV is identity-stateless.

# ── Movement Analysis ─────────────────────────────────────────────────────────

@app.post("/classify")
async def classify(
    video: UploadFile = File(...),
    track_id: int = Form(...),
    reference_dir: Optional[str] = Form(None),
    min_confidence: float = Form(0.75),
):
    """Identify which exercise a tracked person is performing."""
    tmp = _save_upload(video)
    try:
        return pipeline.classify_movement(tmp, track_id, reference_dir, min_confidence)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        os.unlink(tmp)


@app.post("/movement_context")
async def movement_context(
    video: UploadFile = File(...),
    track_id: int = Form(...),
    min_confidence: float = Form(0.75),
):
    """
    Return full OOD context for a person's movement.
    When is_ood=True, the agent uses search_hint to find a reference video,
    then calls /check_reference to verify it, then /add_exercise_reference.
    """
    tmp = _save_upload(video)
    try:
        return pipeline.get_movement_context(tmp, track_id, min_confidence=min_confidence)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        os.unlink(tmp)


@app.post("/extract_keypoints")
async def extract_keypoints(
    video: UploadFile = File(...),
    track_id: int = Form(...),
    num_frames: int = Form(32),
):
    """Extract MediaPipe pose keypoints for a specific tracked person."""
    tmp = _save_upload(video)
    try:
        return pipeline.extract_keypoints(tmp, track_id, num_frames)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        os.unlink(tmp)


@app.post("/analyze_form")
async def analyze_form(
    video: UploadFile = File(...),
    track_id: int = Form(...),
    min_confidence: float = Form(0.75),
):
    """
    classify_movement + extract_keypoints in one call.
    coaching_notes in the response is None — to be populated by the agent layer.
    """
    tmp = _save_upload(video)
    try:
        return pipeline.analyze_form(tmp, track_id, min_confidence=min_confidence)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        os.unlink(tmp)


# ── OOD / Reference Quality ───────────────────────────────────────────────────

@app.post("/check_reference")
async def check_reference(
    query_video: UploadFile = File(...),
    reference_video: UploadFile = File(...),
    query_track_id: int = Form(...),
    threshold: float = Form(0.75),
):
    """
    Test whether a downloaded video is a good reference match for a query person.
    Part of the agent OOD flow:
      1. /movement_context → is_ood=True, search_hint
      2. agent downloads candidate video
      3. /check_reference → is_good_match
      4. /add_exercise_reference if is_good_match=True
    """
    tmp_q = _save_upload(query_video)
    tmp_r = _save_upload(reference_video)
    try:
        return pipeline.check_reference_quality(tmp_q, query_track_id, tmp_r, threshold)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        os.unlink(tmp_q)
        os.unlink(tmp_r)


# ── Live Streaming (RTSP today, WebRTC later) ────────────────────────────────

_live: dict = {"session": None}

# Set whenever a session is created; cleared on stop. Lets /live/events
# block waiting for a session instead of disconnecting.
_session_ready: asyncio.Event = asyncio.Event()


@app.post("/live/start")
async def live_start(
    security_url: str = Form(...),
    detail_url: str = Form(...),
):
    """
    Start a live session that consumes two RTSP feeds (or any URL OpenCV can open).

    security_url is the wide POV used for face identification + tracking.
    detail_url is the close-up POV used for higher-fidelity pose extraction.

    Phone setup: install an RTSP camera app (e.g. "RTSP Camera Server" on iOS,
    "IP Webcam" on Android), or relay both phones through MediaMTX and pass
    the relay URLs here.
    """
    if _live["session"] is not None:
        raise HTTPException(status_code=409, detail="Live session already running. Call /live/stop first.")
    session = LiveSession()
    try:
        session.add_stream("security", security_url)
        session.add_stream("detail", detail_url)
        session.start()
    except Exception as e:
        session.stop()
        raise HTTPException(status_code=400, detail=f"Failed to start session: {e}")
    _live["session"] = session
    _session_ready.set()
    return {"status": "started", "streams": ["security", "detail"]}


_pcs: set = set()


@app.post("/live/start_webrtc")
async def live_start_webrtc():
    """
    Initialize an empty live session ready to accept WebRTC broadcasts.
    Each phone then opens /broadcast?stream=<name> in mobile Safari.
    """
    if _live["session"] is not None:
        raise HTTPException(status_code=409, detail="Live session already running. Call /live/stop first.")
    session = LiveSession()
    session.start()
    _live["session"] = session
    _session_ready.set()
    return {"status": "ready", "broadcast_urls": {
        "security": "/broadcast?stream=security",
        "detail":   "/broadcast?stream=detail",
    }}


@app.post("/webrtc/offer")
async def webrtc_offer(payload: dict):
    """
    Signaling endpoint: phone POSTs an SDP offer + stream name; server
    creates a peer connection, attaches the inbound video track to the
    LiveSession, and returns the SDP answer.
    """
    try:
        from aiortc import RTCPeerConnection, RTCSessionDescription
    except ImportError:
        raise HTTPException(status_code=500, detail="aiortc not installed. pip install aiortc")

    session = _live["session"]
    if session is None:
        raise HTTPException(status_code=400, detail="Call POST /live/start_webrtc first.")

    stream_name = payload.get("stream")
    if not stream_name:
        raise HTTPException(status_code=400, detail="Missing 'stream' in payload.")

    pc = RTCPeerConnection()
    _pcs.add(pc)
    loop = asyncio.get_running_loop()

    @pc.on("track")
    def on_track(track):
        if track.kind != "video":
            return
        source = WebRtcFrameSource(track, loop)
        try:
            session.add_stream_source(stream_name, source)
        except ValueError:
            # Stream already exists from a previous broadcast — replace it,
            # otherwise the worker keeps reading from the dead source forever.
            session.replace_stream_source(stream_name, source)

    @pc.on("connectionstatechange")
    async def on_state_change():
        if pc.connectionState in ("failed", "closed"):
            _pcs.discard(pc)
            await pc.close()

    offer = RTCSessionDescription(sdp=payload["sdp"], type=payload["type"])
    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    return {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}


# ── Identity (ArUco check-in / checkout / events) ─────────────────────────────

class CheckInRequest(BaseModel):
    patient_id: str


def _require_session() -> LiveSession:
    session = _live["session"]
    if session is None:
        raise HTTPException(status_code=400, detail="No live session running. Start one first.")
    return session


@app.post("/live/check_in")
async def live_check_in(payload: CheckInRequest):
    """
    Start watching the ArUco marker for this patient.
    The patient's phone then shows GET /live/marker.png; once seen in-frame,
    identity emits patient_checked_in on /live/events and the binding sticks.
    """
    session = _require_session()
    session.identity.expect_check_in(payload.patient_id)
    return {"status": "watching", "patient_id": payload.patient_id, "marker_id": identity.CHECK_IN_MARKER_ID}


@app.post("/live/checkout")
async def live_checkout(payload: CheckInRequest):
    """Drop the identity binding for this patient. Ephemeral CV state is cleared."""
    session = _require_session()
    session.identity.checkout(payload.patient_id)
    return {"status": "checked_out", "patient_id": payload.patient_id}


@app.get("/live/marker.png")
async def live_marker_png():
    """Render the hardcoded check-in ArUco marker. Patient phone displays this fullscreen."""
    png = identity.render_marker_png()
    return Response(content=png, media_type="image/png")


@app.websocket("/live/events")
async def live_events_ws(ws: WebSocket):
    """
    Subscribe to identity lifecycle events. The connection stays open across
    /live/start ↔ /live/stop cycles — if no session exists yet, the handler
    blocks on _session_ready until one is started. The backend keeps a
    long-lived subscriber here for the lifetime of the process.
    """
    await ws.accept()
    loop = asyncio.get_running_loop()

    try:
        while True:
            # Wait until there's a session to listen to.
            await _session_ready.wait()
            session = _live["session"]
            if session is None:                # raced with /live/stop
                continue

            queue: asyncio.Queue[identity.IdentityEvent] = asyncio.Queue(maxsize=64)

            def on_event(ev: identity.IdentityEvent, q=queue) -> None:
                try:
                    loop.call_soon_threadsafe(q.put_nowait, ev)
                except asyncio.QueueFull:
                    pass

            unsubscribe = session.identity.subscribe(on_event)
            try:
                # Pump events until either the session stops or the client disconnects.
                while _session_ready.is_set() and _live["session"] is session:
                    try:
                        ev = await asyncio.wait_for(queue.get(), timeout=0.5)
                    except asyncio.TimeoutError:
                        continue
                    await ws.send_json(ev)
            finally:
                unsubscribe()
    except WebSocketDisconnect:
        pass


@app.get("/viewer", response_class=HTMLResponse)
async def viewer_page():
    """Debug viewer: subscribes to /live/ws and draws bboxes + pose skeletons per stream."""
    return """<!doctype html>
<html><head><meta charset="utf-8"><title>ARES Live Viewer</title>
<style>
 body{font-family:-apple-system,sans-serif;background:#111;color:#eee;margin:0;padding:1rem;}
 h1{font-size:1rem;margin:0 0 0.5rem;}
 #status{font-family:monospace;font-size:0.85rem;color:#9f9;margin-bottom:1rem;}
 .grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem;}
 .stream{background:#000;border-radius:8px;padding:0.5rem;}
 .stream h2{font-size:0.9rem;margin:0 0 0.5rem;color:#0a84ff;font-family:monospace;}
 canvas{width:100%;background:#1a1a1a;border-radius:4px;display:block;}
 .meta{font-family:monospace;font-size:0.75rem;color:#888;margin-top:0.3rem;}
</style></head>
<body>
<h1>ARES Live Viewer</h1>
<div id="status">connecting…</div>
<div class="grid">
  <div class="stream"><h2>security</h2><canvas id="c-security" width="640" height="480"></canvas><div class="meta" id="m-security">no frames yet</div></div>
  <div class="stream"><h2>detail</h2><canvas id="c-detail" width="640" height="480"></canvas><div class="meta" id="m-detail">no frames yet</div></div>
</div>
<script>
// MediaPipe pose connections (33-landmark model).
const POSE_CONNECTIONS = [
  [11,12],[11,13],[13,15],[12,14],[14,16],[11,23],[12,24],[23,24],
  [23,25],[25,27],[27,29],[29,31],[27,31],
  [24,26],[26,28],[28,30],[30,32],[28,32],
  [15,17],[15,19],[15,21],[17,19],
  [16,18],[16,20],[16,22],[18,20],
  [9,10],[0,1],[1,2],[2,3],[3,7],[0,4],[4,5],[5,6],[6,8],
];

const $ = id => document.getElementById(id);
const ctxs = { security: $('c-security').getContext('2d'), detail: $('c-detail').getContext('2d') };
const metas = { security: $('m-security'), detail: $('m-detail') };

// Per-stream framebuffer: collect all detections sharing a frame_idx, then render.
const buffers = { security: { idx: -1, dets: [] }, detail: { idx: -1, dets: [] } };
const counts = { security: 0, detail: 0 };
const lastTs = { security: 0, detail: 0 };

function colorFor(tid) {
  const hues = [200, 50, 320, 130, 20, 280];
  return `hsl(${hues[tid % hues.length]}, 80%, 60%)`;
}

function renderFrame(stream) {
  const buf = buffers[stream];
  const ctx = ctxs[stream];
  const w = ctx.canvas.width, h = ctx.canvas.height;

  // Auto-fit canvas to the first detection's bbox extent (rough estimate of source size).
  // We don't get raw frame width/height over the wire — assume 1280x720 source for scaling.
  const srcW = 1280, srcH = 720;
  ctx.canvas.width = ctx.canvas.clientWidth || 640;
  ctx.canvas.height = ctx.canvas.width * (srcH / srcW);
  const W = ctx.canvas.width, H = ctx.canvas.height;
  const sx = W / srcW, sy = H / srcH;

  ctx.fillStyle = '#1a1a1a';
  ctx.fillRect(0, 0, W, H);

  for (const det of buf.dets) {
    const [x1, y1, x2, y2] = det.bbox;
    const color = colorFor(det.track_id);
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.strokeRect(x1*sx, y1*sy, (x2-x1)*sx, (y2-y1)*sy);
    ctx.fillStyle = color;
    ctx.font = '12px monospace';
    const label = det.patient_id ? `${det.patient_id} (#${det.track_id})` : `#${det.track_id}`;
    ctx.fillText(label, x1*sx + 4, y1*sy - 4);

    // Keypoints are normalized to the bbox crop, so map them back into image space.
    const bw = x2 - x1, bh = y2 - y1;
    const kps = det.keypoints || [];
    if (kps.length) {
      ctx.strokeStyle = 'rgba(200,200,200,0.7)';
      ctx.lineWidth = 1.5;
      for (const [i, j] of POSE_CONNECTIONS) {
        const a = kps[i], b = kps[j];
        if (!a || !b) continue;
        ctx.beginPath();
        ctx.moveTo((x1 + a.x * bw) * sx, (y1 + a.y * bh) * sy);
        ctx.lineTo((x1 + b.x * bw) * sx, (y1 + b.y * bh) * sy);
        ctx.stroke();
      }
      ctx.fillStyle = '#0f0';
      for (const lm of kps) {
        ctx.beginPath();
        ctx.arc((x1 + lm.x * bw) * sx, (y1 + lm.y * bh) * sy, 2, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  }

  metas[stream].textContent =
    `frame #${buf.idx}  ·  ${buf.dets.length} person(s)  ·  ${counts[stream]} msgs  ·  t=${lastTs[stream]}ms`;
}

function handle(msg) {
  if (msg.error) { $('status').textContent = msg.error; return; }
  const stream = msg.stream;
  if (!(stream in buffers)) return;
  counts[stream]++;
  lastTs[stream] = msg.timestamp_ms;
  const buf = buffers[stream];
  if (msg.frame_idx !== buf.idx) {
    // Flush previous frame, start a new one.
    if (buf.dets.length) renderFrame(stream);
    buf.idx = msg.frame_idx;
    buf.dets = [];
  }
  buf.dets.push(msg);
}

const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
const ws = new WebSocket(`${proto}//${location.host}/live/ws`);
ws.onopen    = () => $('status').textContent = 'connected — waiting for frames…';
ws.onclose   = () => $('status').textContent = 'disconnected';
ws.onerror   = e  => $('status').textContent = 'error: ' + e;
ws.onmessage = e  => { try { handle(JSON.parse(e.data)); } catch {} };

// Periodically flush whatever's buffered so the canvas updates even if a frame_idx repeats.
setInterval(() => { for (const s of Object.keys(buffers)) if (buffers[s].dets.length) renderFrame(s); }, 100);
</script>
</body></html>"""


@app.get("/broadcast", response_class=HTMLResponse)
async def broadcast_page(stream: str = "security"):
    """Phone-facing page: captures camera and pushes via WebRTC."""
    return f"""<!doctype html>
<html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ARES Broadcast — {stream}</title>
<style>
 body{{font-family:-apple-system,sans-serif;background:#111;color:#eee;margin:0;padding:1rem;}}
 h1{{font-size:1.2rem;margin:0 0 1rem;}}
 video{{width:100%;border-radius:8px;background:#000;}}
 button{{font-size:1.1rem;padding:0.8rem 1.5rem;margin-top:1rem;border-radius:8px;border:0;background:#0a84ff;color:#fff;width:100%;}}
 button:disabled{{background:#444;}}
 #status{{margin-top:1rem;font-family:monospace;font-size:0.9rem;color:#9f9;}}
 select{{font-size:1rem;padding:0.5rem;border-radius:6px;background:#222;color:#eee;border:1px solid #444;width:100%;margin-bottom:0.5rem;}}
</style></head>
<body>
<h1>ARES — broadcasting as <b>{stream}</b></h1>
<select id="cam"></select>
<video id="preview" autoplay muted playsinline></video>
<button id="start">Start broadcast</button>
<button id="stop" disabled>Stop</button>
<div id="status">idle</div>
<script>
const STREAM = {json.dumps(stream)};
const $ = id => document.getElementById(id);
let pc, localStream;

async function listCams() {{
  const devs = await navigator.mediaDevices.enumerateDevices();
  const cams = devs.filter(d => d.kind === 'videoinput');
  $('cam').innerHTML = cams.map((c,i) => `<option value="${{c.deviceId}}">${{c.label || 'Camera '+(i+1)}}</option>`).join('');
}}

async function start() {{
  $('start').disabled = true;
  $('status').textContent = 'requesting camera…';
  localStream = await navigator.mediaDevices.getUserMedia({{
    video: {{ deviceId: $('cam').value ? {{ exact: $('cam').value }} : undefined,
              width: {{ ideal: 1280 }}, height: {{ ideal: 720 }}, frameRate: {{ ideal: 30 }} }},
    audio: false
  }});
  $('preview').srcObject = localStream;

  pc = new RTCPeerConnection({{ iceServers: [{{ urls: 'stun:stun.l.google.com:19302' }}] }});
  localStream.getTracks().forEach(t => pc.addTrack(t, localStream));

  $('status').textContent = 'creating offer…';
  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);
  // wait for ICE gathering to finish — simplest signaling
  await new Promise(r => {{
    if (pc.iceGatheringState === 'complete') return r();
    pc.addEventListener('icegatheringstatechange', () => {{
      if (pc.iceGatheringState === 'complete') r();
    }});
  }});

  $('status').textContent = 'sending offer to server…';
  const resp = await fetch('/webrtc/offer', {{
    method: 'POST', headers: {{'Content-Type':'application/json'}},
    body: JSON.stringify({{ stream: STREAM, sdp: pc.localDescription.sdp, type: pc.localDescription.type }})
  }});
  if (!resp.ok) {{ $('status').textContent = 'offer failed: '+await resp.text(); return; }}
  const answer = await resp.json();
  await pc.setRemoteDescription(answer);
  $('status').textContent = 'broadcasting ✔';
  $('stop').disabled = false;
}}

function stop() {{
  if (pc) pc.close();
  if (localStream) localStream.getTracks().forEach(t => t.stop());
  $('status').textContent = 'stopped';
  $('start').disabled = false; $('stop').disabled = true;
}}

$('start').onclick = start;
$('stop').onclick = stop;
navigator.mediaDevices.getUserMedia({{video:true,audio:false}}).then(s => {{
  s.getTracks().forEach(t => t.stop());
  listCams();
}}).catch(() => $('status').textContent = 'camera permission needed');
</script>
</body></html>"""


@app.post("/live/stop")
async def live_stop():
    session = _live["session"]
    if session is None:
        raise HTTPException(status_code=404, detail="No live session running.")
    for pc in list(_pcs):
        await pc.close()
        _pcs.discard(pc)
    session.stop()
    _live["session"] = None
    _session_ready.clear()
    return {"status": "stopped"}


@app.get("/live/mjpeg")
async def live_mjpeg():
    """MJPEG stream of the security camera feed. Consumable by cv2.VideoCapture."""
    session = _live["session"]
    if session is None:
        raise HTTPException(status_code=503, detail="No live session running.")

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=30)

    def on_raw_frame(frame: np.ndarray) -> None:
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        try:
            loop.call_soon_threadsafe(queue.put_nowait, buf.tobytes())
        except asyncio.QueueFull:
            pass

    unsubscribe = session.subscribe_raw(on_raw_frame)

    async def generate():
        try:
            while True:
                try:
                    jpg = await asyncio.wait_for(queue.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    break
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
        finally:
            unsubscribe()

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.websocket("/live/ws")
async def live_ws(ws: WebSocket):
    """
    Stream LiveFrame events as JSON to the connected client. Stays open
    across /live/start ↔ /live/stop cycles — if no session exists yet,
    blocks on _session_ready until one starts.
    """
    await ws.accept()
    loop = asyncio.get_running_loop()

    try:
        while True:
            await _session_ready.wait()
            session = _live["session"]
            if session is None:
                continue

            queue: asyncio.Queue[LiveFrame] = asyncio.Queue(maxsize=256)

            def on_frame(frame: LiveFrame, q=queue) -> None:
                try:
                    loop.call_soon_threadsafe(q.put_nowait, frame)
                except asyncio.QueueFull:
                    pass

            unsubscribe = session.subscribe(on_frame)
            try:
                while _session_ready.is_set() and _live["session"] is session:
                    try:
                        frame = await asyncio.wait_for(queue.get(), timeout=0.5)
                    except asyncio.TimeoutError:
                        continue
                    await ws.send_text(json.dumps(frame))
            finally:
                unsubscribe()
    except WebSocketDisconnect:
        pass


@app.post("/add_exercise_reference")
async def add_exercise_reference(
    video: UploadFile = File(...),
    exercise_name: str = Form(...),
):
    """
    Add a new exercise video to the reference library.
    Call after check_reference confirms is_good_match=True.
    Invalidates the reference cache so the new class is picked up immediately.
    """
    tmp = _save_upload(video)
    try:
        pipeline.add_exercise_reference(tmp, exercise_name)
        return {"status": "added", "exercise": exercise_name}
    finally:
        os.unlink(tmp)
