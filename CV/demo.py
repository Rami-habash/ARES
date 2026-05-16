"""
ARES demo — illustrates the offline movement-analysis pipeline.

1. Warm up models and reference embeddings
2. Run YOLO tracking over the clip and list the track_ids seen
3. User picks a track_id
4. Classify movement; if OOD, print agent search context
5. Extract pose keypoints

Live identity (ArUco marker → patient binding) is handled by the live API in
api.py + identity.py, not here.
"""

import cv2

import bounding_box
import pipeline

VIDEO = "7894262-uhd_4096_2160_25fps.mp4"

# ── 1. Startup ────────────────────────────────────────────────────────────────
print("Loading models…")
pipeline.preload_models()

print("Pre-loading reference embeddings…")
pipeline.preload_references()

# ── 2. List track_ids in the clip ─────────────────────────────────────────────
print(f"\nTracking '{VIDEO}' to enumerate persons…")
cap = cv2.VideoCapture(VIDEO)
track_ids: set[int] = set()
while cap.isOpened():
    ok, frame = cap.read()
    if not ok:
        break
    for box in bounding_box.extract_bounding_boxes(pipeline._bbox(), frame, 0.5):
        if box.id is not None:
            track_ids.add(int(box.id[0]))
cap.release()

if not track_ids:
    print("No persons detected. Exiting.")
    raise SystemExit

print(f"\n  Track IDs seen: {sorted(track_ids)}")

# ── 3. Pick a track_id ────────────────────────────────────────────────────────
track_id = int(input(f"\nWhich track_id? {sorted(track_ids)}: "))

# ── 4. Classify movement ──────────────────────────────────────────────────────
print(f"\nClassifying movement for track {track_id}…")
result = pipeline.classify_movement(VIDEO, track_id)

print(f"\n  Prediction : {result['prediction'] or 'OOD — no confident match'}")
print(f"  Confidence : {result['confidence']}")
print(f"\n  All scores:")
for label, score in sorted(result["all_scores"].items(), key=lambda x: -x[1]):
    bar = "█" * int(score * 30)
    print(f"    {label:<30} {score:.3f}  {bar}")

if result["prediction"] is None:
    ctx = pipeline.get_movement_context(VIDEO, track_id)
    print(f"\n  OOD — agent search context:")
    print(f"    search_hint    : {ctx['search_hint']}")
    print(f"    known_exercises: {ctx['known_exercises']}")
    print(f"  → agent should call check_reference_quality after downloading a candidate video")
    print(f"  → then add_exercise_reference if is_good_match=True")

# ── 5. Extract keypoints ──────────────────────────────────────────────────────
print(f"\nExtracting keypoints for track {track_id}…")
kp = pipeline.extract_keypoints(VIDEO, track_id)
detected = sum(1 for frame in kp["landmarks"] if frame)
print(f"  {kp['frame_count']} frames sampled, pose detected in {detected}")
