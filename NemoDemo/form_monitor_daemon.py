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
import logging
import os
import tempfile
import time
from pathlib import Path

import cv2

from form_monitor import Event, FormMonitor, TickResult

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


async def capture_loop(
    source: int | str,
    clip_queue: asyncio.Queue,
    stop_event: asyncio.Event,
):
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        logger.error("Failed to open video source: %r", source)
        stop_event.set()
        return
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    logger.info("Capture started (source=%s, fps=%.1f, clip=%.1fs)", source, fps, CLIP_SECONDS)

    try:
        while not stop_event.is_set():
            clip_path = await asyncio.to_thread(_capture_clip, cap, fps, CLIP_SECONDS)
            if clip_path is None:
                logger.warning("Capture returned no frames; stopping.")
                stop_event.set()
                break
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
                await agent_callback(result)
            except Exception:
                logger.exception("agent_callback raised; continuing")


# ---------------------------------------------------------------------------
# Default agent callback — stub. Wire to NemoClaw transport when known.
# ---------------------------------------------------------------------------

async def default_agent_callback(result: TickResult):
    payload = {
        "event":      result.event.value,
        "state":      result.state.value,
        "exercise":   result.exercise,
        "form_score": result.form_score,
        "note":       result.note,
    }
    print(f"  → AGENT NOTIFY: {payload}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def run(patient_id: str, source: int | str, agent_callback=default_agent_callback):
    monitor    = FormMonitor(patient_id)
    clip_queue: asyncio.Queue = asyncio.Queue(maxsize=2)
    stop_event = asyncio.Event()

    await asyncio.gather(
        capture_loop(source, clip_queue, stop_event),
        process_loop(monitor, clip_queue, agent_callback, stop_event),
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

    # Cast --source: int if it's a digit, else use as a file path.
    source: int | str = int(args.source) if args.source.isdigit() else args.source

    # keypoint_extraction looks for pose_landmarker_full.task relative to cwd.
    os.chdir(Path(__file__).resolve().parent.parent / "CV")

    try:
        asyncio.run(run(args.patient, source))
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
