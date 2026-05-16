"""Test that the PATIENT_PAUSED event fires after exercise stops."""
import os
import sys
import tempfile
from pathlib import Path

os.chdir(Path(__file__).resolve().parent.parent / "CV")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "CV"))

import cv2
import numpy as np
from form_monitor import Event, FormMonitor, State


def make_static_clip(h: int = 480, w: int = 640, n_frames: int = 8) -> str:
    fd, path = tempfile.mkstemp(suffix=".mp4", prefix="static_")
    os.close(fd)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(path, fourcc, 30.0, (w, h))
    frame = np.full((h, w, 3), 128, dtype=np.uint8)
    for _ in range(n_frames):
        writer.write(frame)
    writer.release()
    return path


def main():
    monitor = FormMonitor("P001")
    squat = str(Path(__file__).resolve().parent / "data/videos/squat/squat_10.mp4")

    print("Tick 1 — exercise clip (expect EXERCISE_IDENTIFIED)...")
    r1 = monitor.tick(squat)
    print(f"  state={r1.state.value}  event={r1.event}  note={r1.note!r}")
    assert r1.event == Event.EXERCISE_IDENTIFIED, f"Expected EXERCISE_IDENTIFIED, got {r1.event}"
    assert monitor.state == State.MONITORING

    static = make_static_clip()
    try:
        print("Tick 2 — static clip (expect PATIENT_PAUSED)...")
        r2 = monitor.tick(static)
        print(f"  state={r2.state.value}  event={r2.event}  note={r2.note!r}")
        assert r2.event == Event.PATIENT_PAUSED, f"Expected PATIENT_PAUSED, got {r2.event}"
        assert monitor.state == State.WAITING
    finally:
        os.unlink(static)

    print("\nPASS")


if __name__ == "__main__":
    main()
