# Live Streaming

The CV pipeline accepts live video from two phone cameras via either RTSP
(LAN-only, needs an RTSP camera app) or WebRTC (no app, works from mobile
Safari). Both routes feed the same `LiveSession` through the `FrameSource`
abstraction in [frame_source.py](frame_source.py), so the pipeline code is
identical regardless of transport.

---

## WebRTC (recommended — no phone app, free)

### One-time install

```bash
pip install aiortc
brew install ngrok           # or download from https://ngrok.com
ngrok config add-authtoken <your-token>   # free signup at ngrok.com
```

### Run

```bash
# 1. Start the API
cd CV && uvicorn api:app --host 0.0.0.0 --port 8000

# 2. In another terminal, expose it via HTTPS (mobile Safari requires it for camera access)
ngrok http 8000
# → Forwarding  https://abc-123.ngrok.app -> http://localhost:8000

# 3. Initialize the live session
curl -X POST https://abc-123.ngrok.app/live/start_webrtc

# 4. On each phone, open Safari and go to:
#    Phone A (security cam): https://abc-123.ngrok.app/broadcast?stream=security
#    Phone B (detail cam):   https://abc-123.ngrok.app/broadcast?stream=detail
#    Pick the rear camera, tap "Start broadcast", grant camera permission.

# 5. Subscribe to per-frame events
websocat wss://abc-123.ngrok.app/live/ws

# 6. When done
curl -X POST https://abc-123.ngrok.app/live/stop
```

### How it works

The phone page calls `getUserMedia` for the rear camera, creates an
`RTCPeerConnection`, POSTs an SDP offer to `/webrtc/offer`, and the server
attaches the inbound video track to the live session as a
`WebRtcFrameSource`. Frames flow:

```
Phone Safari ──H.264 / WebRTC──► aiortc ──► WebRtcFrameSource ──► LiveSession ──► /live/ws (JSON)
                                   ▲                                  │
                                   └── /webrtc/offer (signaling) ─────┘
```

Latency: ~150–300ms end-to-end on a decent Wi-Fi.

---

## RTSP (alternative — needs an RTSP-capable iOS app)

Use this if you have a paid app like *Live-Reporter* or *RTSP Camera Server*
that exposes `rtsp://<phone-ip>:8554/...`, or if you're running MediaMTX as a
push relay for free RTMP push apps (Larix, etc).

```bash
# Same Wi-Fi, phone serves RTSP directly
curl -X POST http://localhost:8000/live/start \
  -F security_url=rtsp://192.168.1.42:8554/stream \
  -F detail_url=rtsp://192.168.1.43:8554/stream
```

With MediaMTX as a relay (`docker run --rm -it --network=host bluenviron/mediamtx`),
phones push to `rtmp://<server>:1935/security` and `rtmp://<server>:1935/detail`,
and the server reads `rtsp://localhost:8554/security` and `…/detail`.

---

## How the two streams are used

- `security` — wide POV, owns identity. face_id runs here, results cache
  per `track_id`, and `patient_id` is propagated.
- `detail` — close-up POV, runs the same YOLO+MediaPipe but doesn't own
  identity; its `patient_id` is filled in once the security stream resolves
  the same `track_id`.

Cross-camera re-identification (matching the same person between security
and detail views) is a known limitation — both streams currently have
independent track-id namespaces.
