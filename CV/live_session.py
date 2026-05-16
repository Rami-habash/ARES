"""
LiveSession — runs the CV pipeline against live FrameSources.

A session has named streams (typically "security" and "detail"). Each stream
is processed in its own background thread: read frame → YOLO bbox+track →
(optional pose) → emit LiveFrame to subscribers.

Identity is established by detecting an ArUco marker the patient holds up
on their phone (see identity.py). Once a track is bound to a patient_id,
BoT-SORT's appearance ReID keeps the binding glued to the track through
short occlusions; if the tracker loses the patient, identity.py emits a
patient_lost event and the patient is asked to show the marker again.

The detail stream does not own identity — its frames are emitted with
stream="detail" so the consumer can correlate by patient_id once the
security stream has bound it.

Designed to be transport-agnostic: FrameSources can be file/RTSP/WebRTC.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypedDict

import bounding_box
import pipeline
from frame_source import FrameSource, open_source
from identity import IdentityRegistry

log = logging.getLogger("ares.live_session")

# Stream-name conventions. The security worker owns identity (YOLO+ArUco, no
# pose). The detail worker is pose-only (no identity work).
SECURITY_STREAM = "security"
DETAIL_STREAM   = "detail"


class LiveFrame(TypedDict):
    stream:       str                              # "security" | "detail" | custom
    timestamp_ms: int                              # wall-clock since session start
    frame_idx:    int
    frame_w:      int                              # source-frame width  (bbox coords are in this space)
    frame_h:      int                              # source-frame height
    track_id:     int                              # YOLO tracker id
    patient_id:   str | None                       # bound on security stream; None until ArUco check-in
    bbox:         tuple[int, int, int, int]
    keypoints:    list[pipeline.Landmark]          # always [] on the security stream


Subscriber = Callable[[LiveFrame], None]


@dataclass
class _StreamWorker:
    name:   str
    source: FrameSource
    thread: threading.Thread | None = None
    stopped: bool = False
    frame_idx: int = 0


class LiveSession:
    def __init__(self) -> None:
        self._streams: dict[str, _StreamWorker] = {}
        self._subscribers: list[Subscriber] = []
        self._sub_lock = threading.Lock()
        self._started_at: float | None = None
        self.identity = IdentityRegistry()

    # ── subscribers ───────────────────────────────────────────────────────────

    def subscribe(self, fn: Subscriber) -> Callable[[], None]:
        with self._sub_lock:
            self._subscribers.append(fn)

        def unsubscribe() -> None:
            with self._sub_lock:
                if fn in self._subscribers:
                    self._subscribers.remove(fn)

        return unsubscribe

    def _emit(self, frame: LiveFrame) -> None:
        with self._sub_lock:
            subs = list(self._subscribers)
        for fn in subs:
            try:
                fn(frame)
            except Exception:
                pass

    # ── streams ───────────────────────────────────────────────────────────────

    def add_stream(self, name: str, uri: str) -> None:
        self.add_stream_source(name, open_source(uri))

    def add_stream_source(self, name: str, source: FrameSource) -> None:
        """Attach a pre-built FrameSource (e.g. WebRtcFrameSource)."""
        if name in self._streams:
            raise ValueError(f"Stream '{name}' already added")
        worker = _StreamWorker(name=name, source=source)
        self._streams[name] = worker
        # If the session is already running, start the worker immediately so
        # WebRTC streams that arrive after start() are picked up live.
        if self._started_at is not None:
            worker.thread = threading.Thread(
                target=self._run_stream, args=(worker,), daemon=True
            )
            worker.thread.start()

    def replace_stream_source(self, name: str, source: FrameSource) -> None:
        """Hot-swap a stream's FrameSource — used when a phone re-broadcasts
        and the previous WebRTC track went dead. Stops the existing worker,
        releases the old source, and spins up a fresh worker on the new one."""
        old = self._streams.get(name)
        if old is not None:
            old.stopped = True
            if old.thread:
                old.thread.join(timeout=2.0)
            try:
                old.source.release()
            except Exception:
                log.exception("[%s] error releasing old source on replace", name)
            del self._streams[name]
        self.add_stream_source(name, source)

    def start(self) -> None:
        if self._started_at is not None:
            raise RuntimeError("Session already started")
        # Warm only the models the live loop actually uses.
        pipeline._bbox()
        pipeline._pose()
        self._started_at = time.time()
        for worker in self._streams.values():
            worker.thread = threading.Thread(
                target=self._run_stream, args=(worker,), daemon=True
            )
            worker.thread.start()

    def stop(self) -> None:
        for worker in self._streams.values():
            worker.stopped = True
        for worker in self._streams.values():
            if worker.thread:
                worker.thread.join(timeout=2.0)
            worker.source.release()
        self.identity.stop()

    # ── per-stream loop ───────────────────────────────────────────────────────

    def _run_stream(self, worker: _StreamWorker) -> None:
        bbox_model = pipeline._bbox()
        run_pose = worker.name != SECURITY_STREAM
        if run_pose:
            pipeline._pose()  # warm

        log.info("[%s] worker started (pose=%s)", worker.name, run_pose)
        first_frame_logged = False

        while not worker.stopped:
            try:
                ok, frame = worker.source.read()
                if not ok or frame is None:
                    continue

                if not first_frame_logged:
                    log.info("[%s] first frame received (shape=%s)", worker.name, frame.shape)
                    first_frame_logged = True

                h, w = frame.shape[:2]
                timestamp_ms = int((time.time() - (self._started_at or time.time())) * 1000)

                tracks: list[tuple[int, tuple[int, int, int, int]]] = []
                for box in bounding_box.extract_bounding_boxes(bbox_model, frame, 0.5):
                    if box.id is None:
                        continue
                    tid = int(box.id[0])
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    x1, y1 = max(0, x1), max(0, y1)
                    x2, y2 = min(w, x2), min(h, y2)
                    tracks.append((tid, (x1, y1, x2, y2)))

                # Security stream owns identity: detect ArUco and refresh bindings.
                if worker.name == SECURITY_STREAM and tracks:
                    self.identity.observe_frame(frame, tracks)

                for tid, (x1, y1, x2, y2) in tracks:
                    if run_pose:
                        crop = frame[y1:y2, x1:x2]
                        keypoints = (
                            pipeline._landmarks_from_crop(crop, timestamp_ms)
                            if crop.size > 0
                            else []
                        )
                    else:
                        keypoints = []

                    self._emit(LiveFrame(
                        stream=worker.name,
                        timestamp_ms=timestamp_ms,
                        frame_idx=worker.frame_idx,
                        frame_w=w,
                        frame_h=h,
                        track_id=tid,
                        patient_id=self.identity.patient_for_track(tid),
                        bbox=(x1, y1, x2, y2),
                        keypoints=keypoints,
                    ))

                worker.frame_idx += 1
            except Exception:
                log.exception("[%s] worker error on frame %d", worker.name, worker.frame_idx)
                time.sleep(0.1)
