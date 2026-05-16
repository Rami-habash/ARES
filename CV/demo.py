"""
ARES demo — illustrates the full pipeline interface.

1. Warm up models and reference embeddings
2. Scan video → identify / auto-enroll all persons
3. User picks a person (track_id)
4. Classify movement; if OOD, print agent search context
5. Extract pose keypoints
"""

import pipeline

VIDEO = "7894262-uhd_4096_2160_25fps.mp4"

# ── 1. Startup ────────────────────────────────────────────────────────────────
print("Loading models…")
pipeline.preload_models()

print("Pre-loading reference embeddings…")
pipeline.preload_references()

# ── 2. Scan for persons ───────────────────────────────────────────────────────
print(f"\nScanning '{VIDEO}'…")
persons = pipeline.scan_persons(VIDEO)

if not persons:
    print("No persons detected. Exiting.")
    raise SystemExit

print("\n  Detected persons:")
for p in persons:
    status = "NEW  " if p["is_new"] else "known"
    name   = p["patient_name"] or "Unknown"
    print(f"    Track {p['track_id']:3d}  [{status}]  {name}  (id: {p['patient_id']}, face confidence: {p['confidence']:.3f})")

# ── 3. Pick a person ──────────────────────────────────────────────────────────
track_ids = [p["track_id"] for p in persons]
track_id  = int(input(f"\nWhich track_id? {track_ids}: "))

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

print(f"\n{'─'*45}")
print("Session patient map:", {p["patient_id"]: p["track_id"] for p in persons})
print("Call pipeline.track_all_patients(VIDEO) to stream per-frame data for all patients.")
