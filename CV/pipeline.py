"""
ARES Pipeline — unified agent interface.

Models are loaded lazily on first call and reused. All public functions accept
plain types (str paths, int IDs) and return TypedDicts that are directly
JSON-serialisable so they can be passed to / returned from any agent layer.

Quick reference
───────────────
Startup
  preload_models()                                         warm all models
  preload_references(reference_dir?)                       warm reference cache

Patient management
  scan_persons(video_path)                                 → list[PersonResult]
  register_patient(video_path, name, exercises?)           → str (patient_id)
  get_patient(patient_id)                                  → PatientResult
  list_patients()                                          → list[PatientResult]
  assign_exercises(patient_id, exercises)

Movement analysis — single person
  classify_movement(video_path, track_id, ...)             → MovementResult
  get_movement_context(video_path, track_id, ...)          → OODContext
  extract_keypoints(video_path, track_id, num_frames?)     → KeypointResult
  extract_reference_keypoints(reference_video, num_frames?) → list[list[Landmark]]
  analyze_form(video_path, track_id, ...)                  → FormResult
  compare_form(video_path, track_id, reference_video, ...) → FormComparison

OOD / reference quality (agent internet-retrieval flow)
  check_reference_quality(query_video, track_id, ref_video, threshold?)
                                                           → ReferenceCheckResult
  add_exercise_reference(video_path, exercise_name, ref_dir?)

Multi-patient streaming (requires scan_persons to have been called first)
  track_all_patients(video_path, on_frame?)                → dict[patient_id, list[PatientFrame]]
  track_and_log_patient(video_path, patient_id, on_frame?) → list[PatientFrame]
"""

from __future__ import annotations

import sys as _sys
_sys.modules.setdefault("tensorflow", None)  # prevents keras→pandas→pyarrow mutex crash with ONNX Runtime on macOS

import json
import shutil
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import TypedDict

import cv2
import numpy as np
import torch

import bounding_box
import face_id
import form_analysis
import keypoint_extraction
import video_embeder

from form_analysis import (     # noqa: F401 — re-exported so callers only need pipeline
    FormComparison,
    JointDeviation,
    PhaseStats,
    SymmetryAnalysis,
)

# ── Paths ─────────────────────────────────────────────────────────────────────

CACHE_ROOT      = Path(__file__).parent / "data" / "embeddings"
DEFAULT_REF_DIR = Path(__file__).parent / "workout_videos"
VIDEO_EXTS      = {".mp4", ".avi", ".mov", ".mkv", ".webm"}

# ── Return Types ──────────────────────────────────────────────────────────────

class PersonResult(TypedDict):
    track_id:     int
    patient_id:   str
    patient_name: str | None
    is_new:       bool
    confidence:   float


class PatientResult(TypedDict):
    patient_id:         str
    name:               str
    assigned_exercises: list[str]


class MovementResult(TypedDict):
    prediction:  str | None        # best label, or None if OOD
    confidence:  float | None
    all_scores:  dict[str, float]


class OODContext(TypedDict):
    """
    Returned when a movement is out-of-distribution.
    Pass this to the agent so it can search the internet for a matching reference.
    """
    is_ood:          bool
    best_match:      str | None    # closest known class even if below threshold
    best_score:      float
    all_scores:      dict[str, float]
    known_exercises: list[str]
    search_hint:     str           # ready-made query string for the agent


class ReferenceCheckResult(TypedDict):
    """
    Result of testing a downloaded video against the query person's movement.
    If is_good_match is True, call add_exercise_reference to persist it.
    """
    reference_video: str
    similarity:      float
    is_good_match:   bool
    threshold_used:  float


class Landmark(TypedDict):
    x:          float
    y:          float
    z:          float
    visibility: float


class KeypointResult(TypedDict):
    track_id:    int
    frame_count: int
    landmarks:   list[list[Landmark]]   # [frame_idx][landmark_idx]


class FormResult(TypedDict):
    track_id:            int
    movement:            str | None
    movement_confidence: float | None
    keypoints:           KeypointResult
    coaching_notes:      str | None     # None here; populated by the agent layer


class PatientFrame(TypedDict):
    """One frame of activity data for a single patient — building block for logs."""
    timestamp_ms: int
    frame_idx:    int
    track_id:     int
    bbox:         tuple[int, int, int, int]   # x1, y1, x2, y2
    keypoints:    list[Landmark]              # empty list if pose not detected


# ── Model Singletons ──────────────────────────────────────────────────────────

_models: dict = {}


def _bbox():
    if "bbox" not in _models:
        _models["bbox"] = bounding_box.load_model()
    return _models["bbox"]


def _s3d():
    if "s3d" not in _models:
        _models["s3d"] = video_embeder.load_model()
    return _models["s3d"]


def _face():
    if "face" not in _models:
        _models["face"] = face_id.load_model()
    return _models["face"]


def _pose():
    if "pose" not in _models:
        _models["pose"] = keypoint_extraction.load_model()
    return _models["pose"]


def preload_models() -> None:
    """Eagerly initialise all models. Call once at startup to avoid first-call latency."""
    # face (ONNX Runtime) and bbox (YOLO) must initialize before PyTorch claims the MPS
    # thread pool — on macOS this ordering prevents a mutex lock crash at startup.
    _face(); _bbox(); _pose(); _s3d()


# ── Reference Embedding Cache ─────────────────────────────────────────────────

_ref_cache: dict[str, np.ndarray] | None = None
_ref_cache_dir: str | None = None


def _cache_path(video_path: Path, reference_dir: Path) -> Path:
    try:
        rel = video_path.relative_to(reference_dir)
    except ValueError:
        rel = Path(video_path.name)
    return CACHE_ROOT / rel.parent / (rel.stem + ".pt")


def _load_reference_embeddings(reference_dir: str | None = None) -> dict[str, np.ndarray]:
    global _ref_cache, _ref_cache_dir
    ref_dir_str = str(Path(reference_dir) if reference_dir else DEFAULT_REF_DIR)
    if _ref_cache is not None and _ref_cache_dir == ref_dir_str:
        return _ref_cache

    ref_path = Path(ref_dir_str)
    type_to_embd: dict[str, list[np.ndarray]] = defaultdict(list)
    for cat in sorted(d for d in ref_path.iterdir() if d.is_dir()):
        for vf in sorted(f for f in cat.iterdir() if f.suffix.lower() in VIDEO_EXTS):
            cache = _cache_path(vf, ref_path)
            if cache.exists():
                emb = torch.load(cache, weights_only=True).numpy()
            else:
                emb = video_embeder.embed(_s3d(), str(vf))
                cache.parent.mkdir(parents=True, exist_ok=True)
                torch.save(torch.from_numpy(emb), cache)
            type_to_embd[cat.name].append(emb)

    _ref_cache = {k: np.stack(v) for k, v in type_to_embd.items() if v}
    _ref_cache_dir = ref_dir_str
    return _ref_cache


def preload_references(reference_dir: str | None = None) -> None:
    """Pre-load and cache all reference video embeddings."""
    _load_reference_embeddings(reference_dir)


# ── Session State ─────────────────────────────────────────────────────────────
# scan_persons populates this map so track_and_log_patient / track_all_patients
# can be called with just a patient_id.

_session_track_map: dict[str, int] = {}   # patient_id → track_id


# ── Internal Helpers ──────────────────────────────────────────────────────────

def _collect_track_boxes(
    video_path: str, track_id: int
) -> list[tuple[int, tuple[int, int, int, int]]]:
    """Sequential YOLO pass → [(frame_idx, (x1,y1,x2,y2)), ...] for one track."""
    cap = cv2.VideoCapture(video_path)
    frames: list[tuple[int, tuple[int, int, int, int]]] = []
    idx = 0
    while cap.isOpened():
        ok, frame = cap.read()
        if not ok:
            break
        h, w = frame.shape[:2]
        for box in bounding_box.extract_bounding_boxes(_bbox(), frame, 0.5):
            if box.id is None:
                continue
            if int(box.id[0]) == track_id:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                frames.append((idx, (max(0, x1), max(0, y1), min(w, x2), min(h, y2))))
        idx += 1
    cap.release()
    return frames


def _embed_person(video_path: str, track_id: int) -> np.ndarray:
    """S3D embedding for a specific tracked person (person-cropped clip)."""
    track_frames = _collect_track_boxes(video_path, track_id)
    if not track_frames:
        raise ValueError(f"Track ID {track_id} not found in '{video_path}'.")

    sample_idxs = np.linspace(0, len(track_frames) - 1, video_embeder.NUM_FRAMES, dtype=int)
    sampled = [track_frames[i] for i in sample_idxs]

    cap = cv2.VideoCapture(video_path)
    crops: list[np.ndarray] = []
    blank = np.zeros((*video_embeder.FRAME_SIZE, 3), dtype=np.uint8)

    for fi, (x1, y1, x2, y2) in sampled:
        cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
        ok, frame = cap.read()
        if not ok or frame is None:
            crops.append(blank)
            continue
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            crops.append(blank)
            continue
        crops.append(cv2.resize(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB), video_embeder.FRAME_SIZE))

    cap.release()

    arr = (np.stack(crops) / 255.0).astype(np.float32)
    tensor = torch.from_numpy(arr).permute(3, 0, 1, 2).unsqueeze(0).to(video_embeder.get_device())
    with torch.no_grad():
        emb = _s3d()(tensor).squeeze(0).cpu().numpy()
    return (emb / np.linalg.norm(emb)).astype(np.float32)


def _landmarks_from_crop(crop: np.ndarray, timestamp_ms: int) -> list[Landmark]:
    lm_list = keypoint_extraction.extract_keypoints(_pose(), crop, timestamp_ms)
    if not lm_list:
        return []
    return [
        Landmark(x=lm.x, y=lm.y, z=lm.z, visibility=getattr(lm, "visibility", 1.0))
        for lm in lm_list[0]
    ]


def _track_patients(
    video_path: str,
    patient_ids: set[str],
    on_frame: Callable[[str, PatientFrame], None] | None = None,
) -> dict[str, list[PatientFrame]]:
    """Single YOLO+MediaPipe pass tracking a subset of session patients."""
    track_to_patient = {
        _session_track_map[pid]: pid
        for pid in patient_ids
        if pid in _session_track_map
    }
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    logs: dict[str, list[PatientFrame]] = {pid: [] for pid in patient_ids}
    frame_idx = 0

    while cap.isOpened():
        ok, frame = cap.read()
        if not ok:
            break
        h, w = frame.shape[:2]
        timestamp_ms = int(frame_idx * (1000.0 / fps))

        for box in bounding_box.extract_bounding_boxes(_bbox(), frame, 0.5):
            if box.id is None:
                continue
            tid = int(box.id[0])
            patient_id = track_to_patient.get(tid)
            if patient_id is None:
                continue

            x1, y1, x2, y2 = map(int, box.xyxy[0])
            x1, y1, x2, y2 = max(0, x1), max(0, y1), min(w, x2), min(h, y2)
            crop = frame[y1:y2, x1:x2]
            keypoints = _landmarks_from_crop(crop, timestamp_ms) if crop.size > 0 else []

            pf = PatientFrame(
                timestamp_ms=timestamp_ms,
                frame_idx=frame_idx,
                track_id=tid,
                bbox=(x1, y1, x2, y2),
                keypoints=keypoints,
            )
            logs[patient_id].append(pf)
            if on_frame:
                on_frame(patient_id, pf)

        frame_idx += 1

    cap.release()
    return logs


# ── Patient Management ────────────────────────────────────────────────────────

def scan_persons(video_path: str) -> list[PersonResult]:
    """
    Scan a video for all persons.
    - Known patients are matched by face and returned with their patient_id.
    - Unknown persons are auto-enrolled (is_new=True) and given a new patient_id.

    Also establishes the session track map so track_and_log_patient /
    track_all_patients can be called with just a patient_id.
    """
    global _session_track_map
    persons = face_id.identify_persons_in_video(_face(), _bbox(), video_path)
    _session_track_map = {p["patient_id"]: p["track_id"] for p in persons}
    return persons


def register_patient(
    video_path: str,
    name: str,
    exercises: list[str] | None = None,
) -> str:
    """
    Enroll a new patient from a short face video (5–15 s recommended).
    Optionally assign their rehab exercises immediately.
    Returns patient_id.
    """
    patient_id = face_id.register_patient(_face(), video_path, name)
    if exercises:
        assign_exercises(patient_id, exercises)
    return patient_id


def get_patient(patient_id: str) -> PatientResult:
    """Return a patient's profile including name and assigned exercises."""
    meta = face_id._read_metadata(patient_id)
    if not meta:
        raise ValueError(f"No patient found with id '{patient_id}'.")
    return PatientResult(
        patient_id=meta.get("id", patient_id),
        name=meta.get("name", "Unknown"),
        assigned_exercises=meta.get("assigned_exercises", []),
    )


def list_patients() -> list[PatientResult]:
    """Return profiles for all registered patients."""
    return [get_patient(pid) for pid in face_id.load_patient_db()]


def assign_exercises(patient_id: str, exercises: list[str]) -> None:
    """Set (or overwrite) the rehab exercise list for a patient."""
    path = face_id.FACE_DB_DIR / patient_id / "metadata.json"
    if not path.exists():
        raise ValueError(f"No patient found with id '{patient_id}'.")
    meta = json.loads(path.read_text())
    meta["assigned_exercises"] = exercises
    path.write_text(json.dumps(meta, indent=2))


# ── Movement Analysis — Single Person ─────────────────────────────────────────

def classify_movement(
    video_path: str,
    track_id: int,
    reference_dir: str | None = None,
    min_confidence: float = 0.75,
) -> MovementResult:
    """
    Identify which exercise a tracked person is performing.
    Returns prediction=None when confidence is below min_confidence (OOD).
    Call get_movement_context to get agent-ready OOD search context.
    """
    refs = _load_reference_embeddings(reference_dir)
    query_emb = _embed_person(video_path, track_id)

    similarities = {
        label: float(np.mean(video_embeder.compute_similarity(ref_embs, query_emb)))
        for label, ref_embs in refs.items()
    }
    labels = list(similarities.keys())
    scores_arr = np.array(list(similarities.values()))
    best_label = video_embeder.determine_best_match(scores_arr, labels, min_confidence)

    return MovementResult(
        prediction=best_label,
        confidence=round(float(np.max(scores_arr)), 4) if best_label else None,
        all_scores={k: round(v, 4) for k, v in similarities.items()},
    )


def get_movement_context(
    video_path: str,
    track_id: int,
    reference_dir: str | None = None,
    min_confidence: float = 0.75,
) -> OODContext:
    """
    Full similarity context for a person's movement, including OOD flag.

    When is_ood=True, the agent should:
      1. Use search_hint to search the internet for a reference video
      2. Download the candidate video
      3. Call check_reference_quality to verify it matches the query
      4. Call add_exercise_reference if it's a good match
    """
    refs = _load_reference_embeddings(reference_dir)
    query_emb = _embed_person(video_path, track_id)

    similarities = {
        label: float(np.mean(video_embeder.compute_similarity(ref_embs, query_emb)))
        for label, ref_embs in refs.items()
    }
    labels = list(similarities.keys())
    scores_arr = np.array(list(similarities.values()))
    best_idx = int(np.argmax(scores_arr))
    best_score = float(scores_arr[best_idx])
    is_ood = best_score < min_confidence

    hint_parts = ["physical therapy rehabilitation exercise"]
    if labels:
        hint_parts.append(f"not: {', '.join(labels)}")
        hint_parts.append(f"possibly similar to: {labels[best_idx]}")

    return OODContext(
        is_ood=is_ood,
        best_match=labels[best_idx] if not is_ood else None,
        best_score=round(best_score, 4),
        all_scores={k: round(v, 4) for k, v in similarities.items()},
        known_exercises=labels,
        search_hint=", ".join(hint_parts),
    )


def extract_keypoints(
    video_path: str,
    track_id: int,
    num_frames: int = 32,
) -> KeypointResult:
    """
    Extract MediaPipe pose landmarks for a specific tracked person.
    Returns per-frame landmark lists (33 body keypoints each).
    """
    track_frames = _collect_track_boxes(video_path, track_id)
    if not track_frames:
        raise ValueError(f"Track ID {track_id} not found in '{video_path}'.")

    sample_idxs = np.linspace(0, len(track_frames) - 1, min(num_frames, len(track_frames)), dtype=int)
    sampled = [track_frames[i] for i in sample_idxs]

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    all_landmarks: list[list[Landmark]] = []

    for fi, (x1, y1, x2, y2) in sampled:
        cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
        ok, frame = cap.read()
        if not ok:
            all_landmarks.append([])
            continue
        crop = frame[y1:y2, x1:x2]
        timestamp_ms = int(fi * (1000.0 / fps))
        all_landmarks.append(_landmarks_from_crop(crop, timestamp_ms) if crop.size > 0 else [])

    cap.release()
    return KeypointResult(track_id=track_id, frame_count=len(all_landmarks), landmarks=all_landmarks)


def extract_reference_keypoints(
    reference_video: str,
    num_frames: int = 64,
) -> list[list[Landmark]]:
    """
    Extract MediaPipe landmarks from a reference video (single-person clip).
    Crops to the largest detected person per frame for cleaner results.
    Use the output with form_analysis.compute_joint_angles if you need raw angles,
    or pass directly to compare_form.
    """
    return form_analysis.extract_reference_keypoints(_pose(), reference_video, _bbox(), num_frames)


def compare_form(
    video_path: str,
    track_id: int,
    reference_video: str,
    num_frames: int = 64,
) -> FormComparison:
    """
    Compare a patient's movement to a reference video.

    Extracts the patient's keypoints (YOLO-cropped), extracts reference keypoints,
    DTW-aligns the two joint-angle sequences, and returns per-joint deviation scores
    plus a plain-English summary ready for the coaching agent.

    Typical agent flow after classify_movement succeeds:
      1. Locate or download the reference video for the identified exercise
      2. compare_form(video, track_id, reference_video)
      3. Use FormComparison.summary + worst_joints to generate coaching feedback
         and set FormResult.coaching_notes
    """
    patient_kp = extract_keypoints(video_path, track_id, num_frames)
    return form_analysis.compare_form(
        patient_kp["landmarks"], reference_video, _pose(), _bbox(), num_frames
    )


def analyze_form(
    video_path: str,
    track_id: int,
    reference_dir: str | None = None,
    min_confidence: float = 0.75,
) -> FormResult:
    """
    Combined classify_movement + extract_keypoints in one call.
    coaching_notes is None — populate it with agent-generated feedback.
    """
    movement = classify_movement(video_path, track_id, reference_dir, min_confidence)
    kps = extract_keypoints(video_path, track_id)
    return FormResult(
        track_id=track_id,
        movement=movement["prediction"],
        movement_confidence=movement["confidence"],
        keypoints=kps,
        coaching_notes=None,
    )


# ── OOD / Reference Quality ───────────────────────────────────────────────────

def check_reference_quality(
    query_video: str,
    query_track_id: int,
    reference_video: str,
    threshold: float = 0.75,
) -> ReferenceCheckResult:
    """
    Test whether a downloaded video is a good reference match for a query person.

    Agent OOD flow:
      1. classify_movement → prediction=None (OOD)
      2. get_movement_context → search_hint for internet search
      3. agent downloads a candidate video
      4. check_reference_quality → is_good_match
      5. if is_good_match: add_exercise_reference to persist it
      6. classify_movement again → now has a reference to match against
    """
    query_emb = _embed_person(query_video, query_track_id)
    ref_emb   = video_embeder.embed(_s3d(), reference_video)
    similarity = float(np.dot(query_emb, ref_emb))
    return ReferenceCheckResult(
        reference_video=reference_video,
        similarity=round(similarity, 4),
        is_good_match=similarity >= threshold,
        threshold_used=threshold,
    )


def add_exercise_reference(
    video_path: str,
    exercise_name: str,
    reference_dir: str | None = None,
) -> None:
    """
    Add a new exercise video to the reference library and invalidate the cache.
    The video is copied into reference_dir/<exercise_name>/ and its embedding cached.
    """
    global _ref_cache
    ref_dir = Path(reference_dir) if reference_dir else DEFAULT_REF_DIR
    exercise_dir = ref_dir / exercise_name
    exercise_dir.mkdir(parents=True, exist_ok=True)

    dst = exercise_dir / Path(video_path).name
    shutil.copy2(video_path, dst)

    cache = _cache_path(dst, ref_dir)
    emb = video_embeder.embed(_s3d(), str(dst))
    cache.parent.mkdir(parents=True, exist_ok=True)
    torch.save(torch.from_numpy(emb), cache)

    _ref_cache = None   # force reload so the new class is picked up


# ── Multi-patient Streaming ───────────────────────────────────────────────────

def track_all_patients(
    video_path: str,
    on_frame: Callable[[str, PatientFrame], None] | None = None,
) -> dict[str, list[PatientFrame]]:
    """
    Process a full video for ALL patients in one YOLO+MediaPipe pass.
    More efficient than calling track_and_log_patient per patient.

    Requires scan_persons to have been called first for this video.

    on_frame(patient_id, PatientFrame) is called per frame in real time —
    use this for live feedback without waiting for the full video to finish.

    Returns {patient_id: [PatientFrame, ...]} for every patient in the session.
    """
    if not _session_track_map:
        raise ValueError("No active session. Call scan_persons first.")
    return _track_patients(video_path, set(_session_track_map.keys()), on_frame)


def track_and_log_patient(
    video_path: str,
    patient_id: str,
    on_frame: Callable[[PatientFrame], None] | None = None,
) -> list[PatientFrame]:
    """
    Stream per-frame pose + bbox data for a single patient.
    Requires scan_persons to have been called first.

    on_frame(PatientFrame) is called per frame in real time — use this for
    live feedback or logging without waiting for the full video.

    Returns the complete list of PatientFrames for the patient.
    """
    if patient_id not in _session_track_map:
        raise ValueError(f"Patient '{patient_id}' not in current session. Call scan_persons first.")
    wrapped = (lambda pid, pf: on_frame(pf)) if on_frame else None
    return _track_patients(video_path, {patient_id}, wrapped)[patient_id]
