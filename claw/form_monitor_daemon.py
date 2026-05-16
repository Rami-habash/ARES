"""Heartbeat daemon: continuously feeds video clips into FormMonitor.

Architecture
------------
Two concurrent asyncio tasks share a bounded queue:

  capture_loop ──▶ asyncio.Queue ──▶ process_loop
                                          │
                                          ▼
                                   FormMonitor.tick
                                          │
                                          └──▶ agent_callback(event)
                                               (only when event != None)

capture_loop  : reads webcam frames, packages a CLIP_SECONDS-long .mp4
                every cycle, drops it on the queue.
process_loop  : pulls the next clip, runs monitor.tick (heavy CV work in a
                worker thread), forwards interesting events to the agent.

CV calls (cv2, S3D embedding, MediaPipe) are blocking, so they run via
asyncio.to_thread.  The bounded queue applies natural back-pressure: if
processing falls behind, capture_loop blocks until a slot frees up.

The agent callback is pluggable.  By default it logs to stdout; wire it
to NemoClaw (e.g. via subprocess.run on a `nemoclaw <sandbox> send` cmd,
HTTP, or a Unix socket) when you know the right transport.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import subprocess
import tempfile
import time
import wave
from pathlib import Path

import cv2

from form_monitor import Event, FormMonitor, TickResult
from patient_profile.profile import add_session_memory

logger = logging.getLogger("form_monitor_daemon")

# Length of each tick's video clip, in seconds.
CLIP_SECONDS = 2.0


# ---------------------------------------------------------------------------
# Capture
# ---------------------------------------------------------------------------

def _capture_clip(cap: cv2.VideoCapture, fps: float, seconds: float) -> str | None:
    """Read `seconds` worth of frames and write them to a temp .mp4. Blocking."""
    n_frames = max(2, int(fps * seconds))
    frames   = []
    for _ in range(n_frames):
        ok, frame = cap.read()
        if not ok or frame is None:
            break
        frames.append(frame)
    if len(frames) < 2:
        return None

    h, w = frames[0].shape[:2]
    fd, path = tempfile.mkstemp(suffix=".mp4", prefix="monitor_")
    os.close(fd)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(path, fourcc, fps, (w, h))
    for f in frames:
        writer.write(f)
    writer.release()
    return path


def _open_capture(source: int | str) -> cv2.VideoCapture | None:
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        return None
    return cap


async def capture_loop(
    source: int | str,
    clip_queue: asyncio.Queue,
    stop_event: asyncio.Event,
):
    cap = await asyncio.to_thread(_open_capture, source)
    if cap is None:
        logger.error("Failed to open video source: %r", source)
        stop_event.set()
        return
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    logger.info("Capture started (source=%s, fps=%.1f, clip=%.1fs)", source, fps, CLIP_SECONDS)

    try:
        while not stop_event.is_set():
            clip_path = await asyncio.to_thread(_capture_clip, cap, fps, CLIP_SECONDS)
            if clip_path is None:
                # Stream stalled (broadcast paused, patient out of frame, etc).
                # Reconnect rather than dying — daemon outlives transient drops.
                logger.warning("Capture stalled; reconnecting in 2s.")
                cap.release()
                await asyncio.sleep(2.0)
                cap = await asyncio.to_thread(_open_capture, source)
                if cap is None:
                    logger.warning("Reconnect failed; will retry.")
                    await asyncio.sleep(2.0)
                    cap = cv2.VideoCapture("")  # placeholder so finally works
                continue
            await clip_queue.put(clip_path)
    finally:
        cap.release()


# ---------------------------------------------------------------------------
# Processing
# ---------------------------------------------------------------------------

async def process_loop(
    monitor:       FormMonitor,
    clip_queue:    asyncio.Queue,
    agent_callback,
    stop_event:    asyncio.Event,
):
    while not stop_event.is_set():
        try:
            clip_path = await asyncio.wait_for(clip_queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            continue

        try:
            result: TickResult = await asyncio.to_thread(monitor.tick, clip_path)
        except Exception:
            logger.exception("monitor.tick raised; continuing")
            continue
        finally:
            try:
                os.unlink(clip_path)
            except OSError:
                pass

        ts = time.strftime("%H:%M:%S")
        print(f"[{ts}] {result.state.value:<12} {result.note}")

        if result.event is not None:
            try:
                await agent_callback(monitor.patient_id, result)
            except Exception:
                logger.exception("agent_callback raised; continuing")


# ---------------------------------------------------------------------------
# Text-to-speech via NVIDIA Magpie (Riva gRPC)
# ---------------------------------------------------------------------------

RIVA_SERVER      = "grpc.nvcf.nvidia.com:443"
RIVA_FUNCTION_ID = "877104f7-e885-42b9-8de8-f6e4c6303969"
RIVA_VOICE       = "Magpie-Multilingual.EN-US.Aria"
RIVA_SAMPLE_RATE = 22050


def _speak_blocking(text: str) -> None:
    api_key = os.environ.get("NVIDIA_API_KEY", "")
    if not api_key or not text:
        return

    import riva.client

    auth = riva.client.Auth(
        uri=RIVA_SERVER,
        use_ssl=True,
        metadata_args=[
            ["function-id", RIVA_FUNCTION_ID],
            ["authorization", f"Bearer {api_key}"],
        ],
    )
    tts = riva.client.SpeechSynthesisService(auth)
    response = tts.synthesize(
        text,
        voice_name=RIVA_VOICE,
        language_code="en-US",
        sample_rate_hz=RIVA_SAMPLE_RATE,
    )

    fd, wav_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        with wave.open(wav_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit PCM
            wf.setframerate(RIVA_SAMPLE_RATE)
            wf.writeframes(response.audio)
        subprocess.run(["aplay", "-q", wav_path], timeout=30)
    finally:
        try:
            os.unlink(wav_path)
        except OSError:
            pass


async def speak(text: str) -> None:
    try:
        await asyncio.to_thread(_speak_blocking, text)
    except Exception:
        logger.exception("TTS failed")


# ---------------------------------------------------------------------------
# WebSocket broadcast server — pushes coaching text to the frontend.
# ---------------------------------------------------------------------------

WS_PORT = 8765
_ws_clients: set = set()


async def _ws_handler(websocket) -> None:
    _ws_clients.add(websocket)
    logger.info("Frontend connected (total=%d)", len(_ws_clients))
    try:
        await websocket.wait_closed()
    finally:
        _ws_clients.discard(websocket)
        logger.info("Frontend disconnected (total=%d)", len(_ws_clients))


async def broadcast_coaching(patient_id: str, text: str) -> None:
    """Send a coaching message to all connected frontend clients."""
    if not _ws_clients:
        return
    payload = json.dumps({"patient_id": patient_id, "text": text})
    await asyncio.gather(
        *[ws.send(payload) for ws in list(_ws_clients)],
        return_exceptions=True,
    )


# ---------------------------------------------------------------------------
# Agent callback — sends events to the OpenClaw agent via openclaw CLI.
# ---------------------------------------------------------------------------

OPENCLAW_SANDBOX  = "nemo-ares"
OPENCLAW_SESSION  = "+10000000001"   # fixed number → stable session key
BACKEND_BASE      = "http://localhost:8000"

def _build_event_message(patient_id: str, result: TickResult) -> str:
    if result.event == Event.EXERCISE_IDENTIFIED:
        return f"[form_monitor] exercise_identified | patient={patient_id} | exercise={result.exercise}"
    if result.event == Event.PATIENT_PAUSED:
        was = result.exercise or "unknown"
        return f"[form_monitor] patient_paused | patient={patient_id} | was={was}"
    if result.event == Event.FORM_COMPARISON:
        comparison = result.comparison or {}
        context = comparison.get("agent_context", comparison.get("summary", str(comparison)))
        context_inline = context.replace("\n", " ").replace("\r", "")
        return (
            f"[form_monitor] form_comparison | patient={patient_id} | exercise={result.exercise} | "
            f"score={comparison.get('overall_score', '?')} | context={context_inline}"
        )
    return f"[form_monitor] unknown_event | patient={patient_id}"


async def default_agent_callback(patient_id: str, result: TickResult):
    msg = _build_event_message(patient_id, result)
    print(f"  → AGENT: {msg!r}")
    cmd = [
        "openshell", "-g", "nemoclaw",
        "sandbox", "exec", "-n", OPENCLAW_SANDBOX, "--",
        "openclaw", "agent",
        "--to", OPENCLAW_SESSION,
        "--message", msg,
        "--json",
    ]
    try:
        proc = await asyncio.to_thread(
            subprocess.run, cmd,
            capture_output=True, text=True, timeout=120,
        )
        if proc.returncode == 0:
            import json
            try:
                data = json.loads(proc.stdout)
                reply = data.get("result", {}).get("payloads", [{}])[0].get("text", "")
                print(f"  ← AGENT: {reply}")
                await broadcast_coaching(patient_id, reply)
                if result.event == Event.PATIENT_PAUSED and reply and not reply.startswith("⚠️"):
                    exercise = result.exercise or "unknown"
                    highlight = f"{exercise} | {reply}"
                    await asyncio.to_thread(add_session_memory, patient_id, highlight)
            except Exception:
                print(f"  ← AGENT (raw): {proc.stdout[:200]}")
        else:
            logger.warning("openclaw agent exited %d: %s", proc.returncode, proc.stderr[:200])
    except Exception:
        logger.exception("agent_callback: openclaw call failed")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------



async def _fire_session_ended(patient_id: str) -> None:
    """Read session memories and send session_ended event to the agent."""
    import json as _json
    import urllib.request as _urllib_req
    from patient_profile.profile import get_patient_profile

    profile = await asyncio.to_thread(get_patient_profile, patient_id)
    if profile and profile.memories:
        memory_lines = " || ".join(
            f"{m.created_at}: {m.highlight}" for m in profile.memories[-15:]
        )
    else:
        memory_lines = "none"

    msg = f"[form_monitor] session_ended | patient={patient_id} | memories={memory_lines}"
    print(f"  -> AGENT (session_ended): {msg!r}")

    cmd = [
        "openshell", "-g", "nemoclaw",
        "sandbox", "exec", "-n", OPENCLAW_SANDBOX, "--",
        "openclaw", "agent",
        "--to", OPENCLAW_SESSION,
        "--message", msg,
        "--json",
    ]
    try:
        proc = await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, text=True, timeout=120,
        )
        if proc.returncode == 0:
            try:
                data = _json.loads(proc.stdout)
                reply = data.get("result", {}).get("payloads", [{}])[0].get("text", "")
                print(f"  <- AGENT: {reply}")
                await broadcast_coaching(patient_id, reply)
            except Exception:
                print(f"  <- AGENT (raw): {proc.stdout[:200]}")
        else:
            logger.warning("session_ended agent call exited %d: %s", proc.returncode, proc.stderr[:200])
    except Exception:
        logger.exception("_fire_session_ended failed")


async def poll_session_state(
    patient_id: str,
    stop_event: asyncio.Event,
    poll_interval: float = 3.0,
) -> None:
    """Poll backend /gym every few seconds. When the patient disappears from
    the non-LEFT list (meaning they tapped Leave), fire session_ended."""
    import json as _json
    import urllib.request as _urllib_req

    seen_active = False
    logger.info("Session polling started for %s (every %.0fs)", patient_id, poll_interval)
    while not stop_event.is_set():
        try:
            with _urllib_req.urlopen(f"{BACKEND_BASE}/gym", timeout=5) as resp:
                sessions = _json.loads(resp.read())
            patient_active = any(s["patient_id"] == patient_id for s in sessions)
            if patient_active:
                seen_active = True
            elif seen_active:
                logger.info("Patient %s left gym - firing session_ended", patient_id)
                await _fire_session_ended(patient_id)
                stop_event.set()
                return
        except Exception as exc:
            logger.debug("poll_session_state: %s", exc)
        await asyncio.sleep(poll_interval)

def _clear_agent_session():
    """Delete accumulated session history so each daemon run starts fresh."""
    cmd = [
        "openshell", "-g", "nemoclaw",
        "sandbox", "exec", "-n", OPENCLAW_SANDBOX, "--",
        "sh", "-c",
        "rm -f /sandbox/.openclaw/agents/main/sessions/*.jsonl "
        "/sandbox/.openclaw/agents/main/sessions/*.trajectory-path.json "
        "/sandbox/.openclaw/agents/main/sessions/*.trajectory.jsonl",
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=30)
        logger.info("Agent session cleared.")
    except Exception:
        logger.warning("Could not clear agent session; continuing anyway.")


async def run(patient_id: str, source: int | str, agent_callback=default_agent_callback):
    _clear_agent_session()
    monitor    = FormMonitor(patient_id)
    clip_queue: asyncio.Queue = asyncio.Queue(maxsize=2)
    stop_event = asyncio.Event()

    import websockets
    async with websockets.serve(_ws_handler, "0.0.0.0", WS_PORT):
        logger.info("Coaching WebSocket listening on ws://0.0.0.0:%d", WS_PORT)
        await asyncio.gather(
            capture_loop(source, clip_queue, stop_event),
            process_loop(monitor, clip_queue, agent_callback, stop_event),
            poll_session_state(patient_id, stop_event),
        )


def main():
    parser = argparse.ArgumentParser(description="Form-monitor heartbeat daemon")
    parser.add_argument("--patient", required=True, help="Patient ID, e.g. P001")
    parser.add_argument(
        "--source",
        default="0",
        help="Video source: webcam index (e.g. '0') or path to a video file",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )

    # Cast --source: int if digit, URL if http(s)://, else resolve as file path
    # (file resolution must happen BEFORE chdir, otherwise relative paths break).
    if args.source.isdigit():
        source: int | str = int(args.source)
    elif args.source.startswith("http://") or args.source.startswith("https://"):
        source = args.source
    else:
        source = str(Path(args.source).resolve())

    # keypoint_extraction looks for pose_landmarker_full.task relative to cwd.
    os.chdir(Path(__file__).resolve().parent.parent / "CV")

    try:
        asyncio.run(run(args.patient, source))
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
