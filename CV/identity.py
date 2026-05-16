"""
Identity binding for the live session — ArUco markers, no facial recognition.

How it works
────────────
1. Patient hits /live/check_in on the backend with their patient_id.
2. Backend tells CV to start watching the single hardcoded ArUco marker for
   that patient_id (one patient at a time for now).
3. Patient holds their phone (showing the marker fullscreen) up to the camera.
4. The security worker calls ``observe_frame`` on each frame: if the marker
   is detected inside any YOLO bbox, that bbox's track_id is bound to the
   watching patient_id and a ``patient_checked_in`` event fires.
5. BoT-SORT's appearance ReID carries the binding through occlusions; the
   lost-track watcher (``_watcher_loop``) fires ``patient_lost`` after
   ``LOST_TIMEOUT_S`` of no sightings, and ``patient_found`` when the marker
   re-binds.
6. /live/checkout drops the binding and forgets the patient.

CV holds no persistent patient data — bindings live only in-process, keyed
by backend-supplied patient_id strings.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal, TypedDict

import cv2
import numpy as np

log = logging.getLogger("ares.identity")

# 4×4 dictionary with 50 IDs. The check-in marker is the first ID in this
# dictionary (CHECK_IN_MARKER_ID below).
ARUCO_DICT = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)

# Detector params: defaults are tuned for printed markers on matte paper.
# We need to handle phone-screen LCDs (subpixel moire) but NOT be so loose
# that wood-grain ceilings, fluorescent reflections, and clothing patterns
# get read as valid markers. Keep the default thresholds for noise rejection
# and only loosen the polygon approx + add corner subpixel refinement.
ARUCO_PARAMS = cv2.aruco.DetectorParameters()
ARUCO_PARAMS.polygonalApproxAccuracyRate = 0.05   # accept slightly warped quads
ARUCO_PARAMS.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
ARUCO_DETECTOR = cv2.aruco.ArucoDetector(ARUCO_DICT, ARUCO_PARAMS)

CHECK_IN_MARKER_ID = 0          # the one marker the demo phone displays
# Rendered PNG: 1000px of marker + 200px white quiet zone on each side.
# Without the quiet zone the detector won't find the marker — phones with
# rounded display corners or dark mode UI eat into it otherwise.
MARKER_PNG_SIZE_PX = 1000
MARKER_QUIET_ZONE_PX = 200

# Total "lost" budget: BoT-SORT keeps a track alive for ~2s after losing it
# (track_buffer=60 in botsort.yaml, ~30 fps). After that, we wait an extra
# 5s before declaring patient_lost — absorbs flaky reacquisitions. Result:
# ~7s of total absence before the patient's phone is asked to show the marker.
LOST_TIMEOUT_S = 5.0

EventType = Literal["patient_checked_in", "patient_lost", "patient_found"]


class IdentityEvent(TypedDict):
    type:        EventType
    patient_id:  str
    track_id:    int | None       # None for patient_lost
    timestamp:   float


EventListener = Callable[[IdentityEvent], None]


@dataclass
class _Binding:
    patient_id:  str
    track_id:    int | None = None     # None while we're still waiting for the marker
    last_seen:   float = field(default_factory=time.time)
    lost:        bool = False


class IdentityRegistry:
    """In-process binding store + lost-track watcher. One instance per session."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_patient: dict[str, _Binding] = {}
        self._listeners: list[EventListener] = []
        self._watcher_stop = threading.Event()
        self._watcher = threading.Thread(target=self._watcher_loop, daemon=True)
        self._watcher.start()

    # ── public API ────────────────────────────────────────────────────────────

    def expect_check_in(self, patient_id: str) -> None:
        """Start watching the marker for this patient. Idempotent."""
        with self._lock:
            self._by_patient.setdefault(patient_id, _Binding(patient_id=patient_id))
            log.info("expect_check_in %s — watching %d patients total", patient_id, len(self._by_patient))

    def checkout(self, patient_id: str) -> None:
        """Drop the binding entirely; stop emitting events for this patient."""
        with self._lock:
            self._by_patient.pop(patient_id, None)

    def patient_for_track(self, track_id: int) -> str | None:
        with self._lock:
            for b in self._by_patient.values():
                if b.track_id == track_id:
                    return b.patient_id
        return None

    def subscribe(self, fn: EventListener) -> Callable[[], None]:
        with self._lock:
            self._listeners.append(fn)
        def unsubscribe() -> None:
            with self._lock:
                if fn in self._listeners:
                    self._listeners.remove(fn)
        return unsubscribe

    def observe_frame(self, frame: np.ndarray, boxes: list[tuple[int, tuple[int, int, int, int]]]) -> None:
        """
        Called once per security-stream frame.

        boxes: [(track_id, (x1, y1, x2, y2)), ...] — all current YOLO tracks.
        Detects ArUco markers in the frame, binds them to whichever box
        contains the marker center, and refreshes last_seen for every bound
        track that is still in view.
        """
        now = time.time()
        marker_to_track = self._aruco_to_track(frame, boxes)

        with self._lock:
            current_track_ids = {tid for tid, _ in boxes}
            events: list[IdentityEvent] = []

            for binding in self._by_patient.values():
                # Marker observation — primary bind / re-bind signal.
                if CHECK_IN_MARKER_ID in marker_to_track:
                    new_tid = marker_to_track[CHECK_IN_MARKER_ID]
                    if binding.track_id != new_tid:
                        was_lost = binding.lost or binding.track_id is None
                        binding.track_id = new_tid
                        binding.last_seen = now
                        if was_lost and binding.track_id is not None and not binding.lost:
                            # First-time bind: checked_in. Re-bind after lost: found.
                            events.append(IdentityEvent(
                                type="patient_checked_in",
                                patient_id=binding.patient_id,
                                track_id=new_tid,
                                timestamp=now,
                            ))
                        elif binding.lost:
                            binding.lost = False
                            events.append(IdentityEvent(
                                type="patient_found",
                                patient_id=binding.patient_id,
                                track_id=new_tid,
                                timestamp=now,
                            ))
                    else:
                        binding.last_seen = now

                # Refresh last_seen if their bound track is still being reported
                # by BoT-SORT, even without the marker visible.
                elif binding.track_id is not None and binding.track_id in current_track_ids:
                    binding.last_seen = now

        for ev in events:
            self._emit(ev)

    # ── internals ─────────────────────────────────────────────────────────────

    def _aruco_to_track(
        self,
        frame: np.ndarray,
        boxes: list[tuple[int, tuple[int, int, int, int]]],
    ) -> dict[int, int]:
        """Detect ArUco markers we care about and assign to the bbox containing them.

        Only markers in `_watched_ids` are logged or returned — the detector
        finds background false positives (wood grain, ceiling lines) and
        logging all of them is noise.
        """
        corners, ids, _ = ARUCO_DETECTOR.detectMarkers(frame)
        if ids is None:
            return {}
        ids_flat = ids.flatten().tolist()
        # Filter to the marker(s) we're actually watching for.
        relevant = [(c, mid) for c, mid in zip(corners, ids_flat) if mid == CHECK_IN_MARKER_ID]
        if not relevant:
            return {}
        out: dict[int, int] = {}
        for marker_corners, marker_id in relevant:
            cx = float(marker_corners[0][:, 0].mean())
            cy = float(marker_corners[0][:, 1].mean())
            matched = False
            for tid, (x1, y1, x2, y2) in boxes:
                if x1 <= cx <= x2 and y1 <= cy <= y2:
                    out[int(marker_id)] = tid
                    matched = True
                    log.info("aruco: marker %d at (%.0f, %.0f) -> track %d", marker_id, cx, cy, tid)
                    break
            if not matched:
                log.info("aruco: marker %d at (%.0f, %.0f) seen but not inside any of %d bbox(es)",
                         marker_id, cx, cy, len(boxes))
        return out

    def _emit(self, event: IdentityEvent) -> None:
        with self._lock:
            listeners = list(self._listeners)
        log.info("event: %s patient=%s track=%s → %d listener(s)",
                 event["type"], event["patient_id"], event["track_id"], len(listeners))
        for fn in listeners:
            try:
                fn(event)
            except Exception:
                log.exception("listener raised on event %s", event)

    def _watcher_loop(self) -> None:
        while not self._watcher_stop.wait(0.5):
            now = time.time()
            stale: list[IdentityEvent] = []
            with self._lock:
                for binding in self._by_patient.values():
                    if (
                        binding.track_id is not None
                        and not binding.lost
                        and (now - binding.last_seen) > LOST_TIMEOUT_S
                    ):
                        binding.lost = True
                        stale.append(IdentityEvent(
                            type="patient_lost",
                            patient_id=binding.patient_id,
                            track_id=None,
                            timestamp=now,
                        ))
            for ev in stale:
                self._emit(ev)

    def stop(self) -> None:
        self._watcher_stop.set()


# ── Marker rendering ──────────────────────────────────────────────────────────

def render_marker_png(marker_id: int = CHECK_IN_MARKER_ID, size: int = MARKER_PNG_SIZE_PX) -> bytes:
    """Return a PNG of the requested ArUco marker with a white quiet-zone border.
    Backend serves this to the patient phone. The quiet zone is mandatory —
    ArUco's outer border has to sit on solid white, or detection fails."""
    marker = cv2.aruco.generateImageMarker(ARUCO_DICT, marker_id, size)
    total = size + 2 * MARKER_QUIET_ZONE_PX
    canvas = np.full((total, total), 255, dtype=np.uint8)
    canvas[
        MARKER_QUIET_ZONE_PX : MARKER_QUIET_ZONE_PX + size,
        MARKER_QUIET_ZONE_PX : MARKER_QUIET_ZONE_PX + size,
    ] = marker
    ok, buf = cv2.imencode(".png", canvas)
    if not ok:
        raise RuntimeError("Failed to encode ArUco marker PNG")
    return buf.tobytes()
