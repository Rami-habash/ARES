"""
Face identification module for physical therapy patient tracking.

Uses InsightFace (ArcFace via buffalo_l) for high-accuracy face recognition.
Designed for recurrent patients: averages embeddings across multiple frames
for a robust per-patient representation stored on disk.

Install: pip install insightface onnxruntime
"""

from __future__ import annotations

import json
import uuid
import numpy as np
import cv2
from pathlib import Path

FACE_DB_DIR = Path(__file__).parent / "data" / "patients"

# ArcFace cosine similarity threshold. Normalised embeddings so dot = cosine.
# 0.40 balances recall vs. precision; raise to 0.45+ for stricter matching.
MATCH_THRESHOLD = 0.40

# Number of video frames to sample when building/comparing face embeddings.
ENROLL_FRAMES = 15
IDENTIFY_FRAMES = 15


def load_model(model_name: str = "buffalo_l"):
    """
    Load InsightFace FaceAnalysis model.
    buffalo_l  — best accuracy (~300 MB, auto-downloads on first use)
    buffalo_s  — faster, lighter (~100 MB)
    """
    try:
        from insightface.app import FaceAnalysis
    except ImportError as e:
        raise ImportError(
            "insightface is required: pip install insightface onnxruntime"
        ) from e

    app = FaceAnalysis(name=model_name, providers=["CPUExecutionProvider"])
    app.prepare(ctx_id=0, det_size=(640, 640))
    return app


def _face_embeddings(model, frame: np.ndarray) -> list[np.ndarray]:
    """Return list of normalised 512-d ArcFace embeddings for each face in the frame."""
    faces = model.get(frame)
    return [f.normed_embedding for f in faces]


# ── Patient DB ───────────────────────────────────────────────────────────────

def load_patient_db() -> dict[str, np.ndarray]:
    """Load all registered patient embeddings keyed by patient_id."""
    FACE_DB_DIR.mkdir(parents=True, exist_ok=True)
    db: dict[str, np.ndarray] = {}
    for d in FACE_DB_DIR.iterdir():
        emb_path = d / "face_embedding.npy"
        if d.is_dir() and emb_path.exists():
            db[d.name] = np.load(emb_path)
    return db


def _read_metadata(patient_id: str) -> dict:
    path = FACE_DB_DIR / patient_id / "metadata.json"
    return json.loads(path.read_text()) if path.exists() else {}


def identify_face(
    embedding: np.ndarray,
    db: dict[str, np.ndarray],
) -> tuple[str | None, float]:
    """
    Nearest-neighbour match against patient DB.
    Returns (patient_id, similarity) or (None, best_score_seen).
    """
    best_id, best_score = None, 0.0
    for pid, ref in db.items():
        score = float(np.dot(embedding, ref))
        if score > best_score:
            best_id, best_score = pid, score
    if best_score >= MATCH_THRESHOLD:
        return best_id, best_score
    return None, best_score


def _enroll_from_embedding(embedding: np.ndarray, name: str = "Unknown") -> str:
    """Save a pre-computed embedding as a new patient record. Returns patient_id."""
    FACE_DB_DIR.mkdir(parents=True, exist_ok=True)
    patient_id = uuid.uuid4().hex[:8]
    patient_dir = FACE_DB_DIR / patient_id
    patient_dir.mkdir(parents=True, exist_ok=True)
    np.save(patient_dir / "face_embedding.npy", embedding)
    (patient_dir / "metadata.json").write_text(
        json.dumps({"id": patient_id, "name": name})
    )
    return patient_id


# ── Patient Registration ─────────────────────────────────────────────────────

def register_patient(model, video_path: str, patient_name: str) -> str:
    """
    Enroll a new patient from a short video clip (5–15 s recommended).
    Samples ENROLL_FRAMES frames, averages face embeddings, saves to DB.
    Returns patient_id.
    """
    cap = cv2.VideoCapture(video_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    sample_idxs = np.linspace(0, total - 1, min(ENROLL_FRAMES, total), dtype=int)

    embeddings: list[np.ndarray] = []
    for idx in sample_idxs:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ok, frame = cap.read()
        if not ok:
            continue
        embs = _face_embeddings(model, frame)
        if embs:
            embeddings.append(embs[0])  # most prominent face per frame

    cap.release()

    if not embeddings:
        raise ValueError("No face detected in the registration video.")

    avg = np.mean(embeddings, axis=0)
    avg = (avg / np.linalg.norm(avg)).astype(np.float32)

    patient_id = uuid.uuid4().hex[:8]
    patient_dir = FACE_DB_DIR / patient_id
    patient_dir.mkdir(parents=True, exist_ok=True)
    np.save(patient_dir / "face_embedding.npy", avg)
    (patient_dir / "metadata.json").write_text(
        json.dumps({"id": patient_id, "name": patient_name})
    )
    return patient_id


# ── Multi-Person Identification ──────────────────────────────────────────────

def identify_persons_in_video(
    face_model,
    bbox_model,
    video_path: str,
    sample_frames: int = IDENTIFY_FRAMES,
) -> list[dict]:
    """
    Process the video sequentially (YOLO tracking needs sequential frames),
    extract face embeddings from sampled frames per tracked person,
    then identify each person against the patient DB.

    Returns:
      [{"track_id": int, "patient_id": str|None, "patient_name": str|None,
        "confidence": float}, ...]
    """
    import bounding_box  # local import to avoid circular dependency at module level

    db = load_patient_db()
    cap = cv2.VideoCapture(video_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    face_sample_set: set[int] = set(
        np.linspace(0, total - 1, min(sample_frames, total), dtype=int).tolist()
    )

    track_embeddings: dict[int, list[np.ndarray]] = {}
    frame_idx = 0

    while cap.isOpened():
        ok, frame = cap.read()
        if not ok:
            break

        boxes = bounding_box.extract_bounding_boxes(bbox_model, frame, 0.5)

        if frame_idx in face_sample_set:
            h, w = frame.shape[:2]
            for box in boxes:
                if box.id is None:
                    continue
                tid = int(box.id[0])
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(w, x2), min(h, y2)
                crop = frame[y1:y2, x1:x2]
                if crop.size == 0:
                    continue
                embs = _face_embeddings(face_model, crop)
                if embs:
                    track_embeddings.setdefault(tid, []).append(embs[0])

        frame_idx += 1

    cap.release()

    persons: list[dict] = []
    for tid, embs in track_embeddings.items():
        avg = np.mean(embs, axis=0)
        avg = (avg / np.linalg.norm(avg)).astype(np.float32)
        pid, score = identify_face(avg, db)
        is_new = False
        if pid is None:
            pid = _enroll_from_embedding(avg)
            db[pid] = avg  # update in-memory db so later tracks can match
            is_new = True
        meta = _read_metadata(pid)
        persons.append(
            {
                "track_id": tid,
                "patient_id": pid,
                "patient_name": meta.get("name"),
                "confidence": round(score, 3),
                "is_new": is_new,
            }
        )

    return persons
