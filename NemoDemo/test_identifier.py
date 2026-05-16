"""
End-to-end test for exercise_identifier.identify_exercise.

Usage
-----
# In-domain: squat is prescribed for P001, expect immediate match
python3 test_identifier.py --patient P001 --video data/videos/squat/squat_10.mp4

# OOD: bench press is not prescribed and has no reference video on disk;
# Nemotron should reason its way to it
python3 test_identifier.py --patient P001 \
  --video ~/.cache/kagglehub/datasets/hasyimabdillah/workoutfitness-video/versions/5/bench\ press/bench_press_1.mp4
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

_NEMO = Path(__file__).resolve().parent
_CV   = _NEMO.parent / "CV"
sys.path.insert(0, str(_CV))
sys.path.insert(0, str(_NEMO))

from exercise_identifier import identify_exercise, _s3d  # noqa: E402
from patient_profile import seed_db, get_patient_profile  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--patient", default="P001")
    parser.add_argument("--video", default="data/videos/squat/squat_10.mp4")
    args = parser.parse_args()

    video_path = Path(args.video)
    if not video_path.is_absolute():
        video_path = _NEMO / video_path
    if not video_path.exists():
        sys.exit(f"Video not found: {video_path}")

    seed_db()
    profile = get_patient_profile(args.patient)
    if profile is None:
        sys.exit(f"Unknown patient: {args.patient}")

    print(f"\nPatient     : {profile.id} — {profile.name}")
    print(f"Prescribed  : {profile.exercises}")
    print(f"Query video : {video_path.name}\n")

    print("Loading S3D model...")
    t0 = time.time()
    import os; os.chdir(_CV)   # keypoint_extraction looks for .task file relative to cwd
    _s3d()
    print(f"  ready in {time.time()-t0:.1f}s\n")

    print("Running identify_exercise...")
    t0 = time.time()
    result = identify_exercise(args.patient, str(video_path))
    elapsed = time.time() - t0

    print(f"\n{'─'*50}")
    print(f"Result  : {result or 'None (identification failed)'}")
    print(f"Time    : {elapsed:.1f}s")
    print(f"{'─'*50}\n")


if __name__ == "__main__":
    main()
