"""
End-to-end test for exercise_identifier.identify_exercise.

Usage
-----
# In-domain test: give it a squat video for P001 (squat is prescribed)
python3 test_identifier.py --patient P001 --video data/videos/squat/squat_10.mp4

# OOD test: give P001 a bench press video (not prescribed, not in reference library)
# The agent should enter the OOD loop and reason its way to 'bench press'
python3 test_identifier.py --patient P001 --video /path/to/bench_press.mp4

The script:
  1. Calls scan_persons on the query video to get the real YOLO track_id
  2. Passes that track_id into identify_exercise
  3. Prints the result and all timing
"""

import argparse
import logging
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)

# ── paths ──────────────────────────────────────────────────────────────────────
_REPO = Path(__file__).resolve().parent.parent
_CV   = _REPO / "CV"
sys.path.insert(0, str(_CV))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pipeline                    # noqa: E402
from exercise_identifier import identify_exercise  # noqa: E402
from patient_profile import seed_db, get_patient_profile  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Test exercise_identifier end-to-end")
    parser.add_argument("--patient", default="P001", help="Patient ID (default: P001)")
    parser.add_argument(
        "--video",
        default="data/videos/squat/squat_10.mp4",
        help="Query video path (relative to NemoDemo/ or absolute)",
    )
    parser.add_argument(
        "--reference-dir",
        default=None,
        help="Override reference video dir (default: NemoDemo/data/videos)",
    )
    args = parser.parse_args()

    video_path = Path(args.video)
    if not video_path.is_absolute():
        video_path = Path(__file__).resolve().parent / video_path
    if not video_path.exists():
        sys.exit(f"Video not found: {video_path}")

    # ── setup ──────────────────────────────────────────────────────────────────
    seed_db()
    profile = get_patient_profile(args.patient)
    if profile is None:
        sys.exit(f"Unknown patient: {args.patient}")

    print(f"\nPatient        : {profile.id} — {profile.name}")
    print(f"Prescribed     : {profile.exercises}")
    print(f"Query video    : {video_path.name}")
    print()

    # ── step 1: warm models ────────────────────────────────────────────────────
    # keypoint_extraction.py resolves pose_landmarker_full.task relative to cwd,
    # so we must be in the CV directory when loading models.
    import os
    os.chdir(_CV)
    print("Loading models (first run downloads S3D weights ~32 MB)...")
    t0 = time.time()
    pipeline.preload_models()
    print(f"  models ready in {time.time()-t0:.1f}s\n")

    # ── step 2: scan to get track_id ──────────────────────────────────────────
    print(f"Scanning '{video_path.name}' for persons...")
    t0 = time.time()
    persons = pipeline.scan_persons(str(video_path))
    print(f"  scan done in {time.time()-t0:.1f}s")

    if not persons:
        sys.exit("No persons detected in the video.")

    for p in persons:
        status = "NEW  " if p["is_new"] else "known"
        print(f"  track {p['track_id']:3d}  [{status}]  confidence={p['confidence']:.3f}")

    track_id = persons[0]["track_id"]
    print(f"\nUsing track_id={track_id}\n")

    # ── step 3: identify exercise ──────────────────────────────────────────────
    print("Running identify_exercise...")
    t0 = time.time()
    result = identify_exercise(args.patient, str(video_path), track_id)
    elapsed = time.time() - t0

    print(f"\n{'─'*50}")
    print(f"Result   : {result or 'None (identification failed)'}")
    print(f"Time     : {elapsed:.1f}s")
    print(f"{'─'*50}\n")


if __name__ == "__main__":
    main()
