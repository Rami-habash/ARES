"""Form-monitor state machine driven by per-tick video clips.

State machine
-------------
    WAITING ──(motion)──▶ IDENTIFYING ──(identified)──▶ MONITORING
       ▲                       │                            │
       │                       │                            │
       └────(no motion)────────┴────────────────────────────┘

WAITING      No patient activity. Tick is a no-op.
IDENTIFYING  Motion detected; classify the clip via identify_exercise.
             Identified → MONITORING.  Not yet → stay IDENTIFYING.
             Motion stops → WAITING.
MONITORING   Score each tick's clip against the identified exercise's
             reference videos.  Motion stops → WAITING; next motion
             re-enters IDENTIFYING (patient may have switched exercises).

This module contains *pure logic* — no I/O, no asyncio, no capture loop.
The capture/scheduling layer lives in form_monitor_daemon.py.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import time

import cv2
import numpy as np

_CV_DIR = Path(__file__).resolve().parent.parent / "CV"
if str(_CV_DIR) not in sys.path:
    sys.path.insert(0, str(_CV_DIR))

import keypoint_extraction  # noqa: E402

from exercise_identifier import identify_exercise  # noqa: E402

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# Mean per-keypoint displacement (normalized 0-1 coords) between adjacent
# sampled frames. Below this → considered stationary.
MOTION_THRESHOLD     = 0.012
MOTION_SAMPLE_FRAMES = 6

# How often (seconds) to forward comparison data to the agent while monitoring.
COMPARISON_INTERVAL_SECS = 3.0


# ---------------------------------------------------------------------------
# Motion detector
# ---------------------------------------------------------------------------

class MotionDetector:
    """Detects whether the patient is moving via MediaPipe keypoint stability."""

    def __init__(self, pose_model=None):
        self._model = pose_model

    def _model_lazy(self):
        if self._model is None:
            self._model = keypoint_extraction.load_model()
        return self._model

    def is_moving(self, clip_path: str) -> bool:
        cap = cv2.VideoCapture(clip_path)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total < 2:
            cap.release()
            return False

        idxs = np.linspace(0, total - 1, min(MOTION_SAMPLE_FRAMES, total), dtype=int)
        keypoint_sets: list[list[tuple[float, float]]] = []

        for fi in idxs:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(fi))
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            kps = keypoint_extraction.extract_keypoints(self._model_lazy(), frame, 0)
            if not kps:
                continue
            keypoint_sets.append([(lm.x, lm.y) for lm in kps[0]])

        cap.release()

        if len(keypoint_sets) < 2:
            return False   # assume stationary if pose detection failed

        displacements = []
        for a, b in zip(keypoint_sets, keypoint_sets[1:]):
            mean_disp = float(np.mean([
                ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5
                for (ax, ay), (bx, by) in zip(a, b)
            ]))
            displacements.append(mean_disp)

        avg = float(np.mean(displacements))
        logger.debug("Motion check: avg keypoint displacement = %.4f (thresh %.4f)",
                     avg, MOTION_THRESHOLD)
        return avg >= MOTION_THRESHOLD


# ---------------------------------------------------------------------------
# Form comparator — STUB
# ---------------------------------------------------------------------------

def compare_to_reference(clip_path: str, exercise_name: str) -> object | None:
    """Compare patient clip to reference videos for *exercise_name*.

    TODO: implementation is owned by another teammate. Return value can be
    any structure the comparator produces — keypoints, joint deviations,
    multi-frame trajectories, etc. Returning None keeps the daemon operational
    while the real implementation lands.
    """
    return None


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

class State(Enum):
    WAITING     = "waiting"
    IDENTIFYING = "identifying"
    MONITORING  = "monitoring"


class Event(Enum):
    PATIENT_PAUSED      = "patient_paused"       # motion stopped — exercise boundary
    EXERCISE_IDENTIFIED = "exercise_identified"  # new exercise classified after motion
    FORM_COMPARISON     = "form_comparison"      # periodic comparison data for agent analysis


@dataclass
class TickResult:
    state:      State
    exercise:   str | None
    comparison: object | None    # raw output of compare_to_reference (any structure)
    event:      Event | None     # set when the agent should be notified
    note:       str              # human-readable summary for logs


class FormMonitor:
    """Stateful per-patient monitor. Call tick(clip_path) on each heartbeat."""

    def __init__(self, patient_id: str):
        self.patient_id = patient_id
        self.state      = State.WAITING
        self.current_exercise: str | None = None
        self._motion    = MotionDetector()
        self._last_comparison_notify: float = 0.0

    def tick(self, clip_path: str) -> TickResult:
        moving = self._motion.is_moving(clip_path)

        # ── Patient is stationary ────────────────────────────────────────────
        if not moving:
            if self.state != State.WAITING:
                prev = self.state
                self.state                   = State.WAITING
                self.current_exercise        = None
                self._last_comparison_notify = 0.0
                return TickResult(
                    state=State.WAITING,
                    exercise=None,
                    comparison=None,
                    event=Event.PATIENT_PAUSED,
                    note=f"patient paused (was {prev.value})",
                )
            return TickResult(State.WAITING, None, None, None, "idle")

        # ── Patient is moving ────────────────────────────────────────────────
        if self.state in (State.WAITING, State.IDENTIFYING):
            self.state = State.IDENTIFYING

            try:
                ex = identify_exercise(self.patient_id, clip_path)
            except Exception as e:
                logger.exception("identify_exercise failed")
                return TickResult(State.IDENTIFYING, None, None, None,
                                  f"identify error: {e}")

            if ex:
                self.current_exercise        = ex
                self.state                   = State.MONITORING
                self._last_comparison_notify = 0.0
                return TickResult(
                    state=State.MONITORING,
                    exercise=ex,
                    comparison=None,
                    event=Event.EXERCISE_IDENTIFIED,
                    note=f"identified: {ex}",
                )

            return TickResult(State.IDENTIFYING, None, None, None,
                              "motion detected, identifying…")

        # ── MONITORING ───────────────────────────────────────────────────────
        try:
            data = compare_to_reference(clip_path, self.current_exercise)
        except Exception as e:
            logger.exception("compare_to_reference failed")
            return TickResult(self.state, self.current_exercise, None, None,
                              f"compare error: {e}")

        if data is None:
            return TickResult(self.state, self.current_exercise, None, None,
                              f"{self.current_exercise} (comparator not yet implemented)")

        now = time.monotonic()
        due = now - self._last_comparison_notify >= COMPARISON_INTERVAL_SECS
        if due:
            self._last_comparison_notify = now
            return TickResult(
                state=self.state,
                exercise=self.current_exercise,
                comparison=data,
                event=Event.FORM_COMPARISON,
                note=f"{self.current_exercise} comparison ready",
            )

        return TickResult(self.state, self.current_exercise, data, None,
                          f"{self.current_exercise} monitoring")
