"""
ARES Movement Analysis API — FastAPI service.

All endpoints are thin wrappers over pipeline.py.
Models and reference embeddings are pre-loaded at startup.

Run:
  cd CV && uvicorn api:app --reload
"""

from __future__ import annotations

import os
import shutil
import tempfile
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

import pipeline


@asynccontextmanager
async def lifespan(app: FastAPI):
    pipeline.preload_models()
    pipeline.preload_references()
    yield


app = FastAPI(title="ARES Movement Analysis API", lifespan=lifespan)


def _save_upload(upload: UploadFile) -> str:
    suffix = os.path.splitext(upload.filename or "")[1] or ".mp4"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    shutil.copyfileobj(upload.file, tmp)
    tmp.close()
    return tmp.name


# ── Patient Management ────────────────────────────────────────────────────────

@app.post("/scan_persons")
async def scan_persons(video: UploadFile = File(...)):
    """
    Scan a video for all persons.
    Known patients are matched; unknowns are auto-enrolled.
    Also establishes the server-side session for track_all_patients.
    """
    tmp = _save_upload(video)
    try:
        return {"persons": pipeline.scan_persons(tmp)}
    finally:
        os.unlink(tmp)


@app.post("/register_patient")
async def register_patient(
    video: UploadFile = File(...),
    name: str = Form(...),
    exercises: str = Form(""),
):
    """
    Enroll a new patient from a short face video (5–15 s).
    exercises: comma-separated list of assigned rehab exercises (optional).
    """
    tmp = _save_upload(video)
    try:
        ex_list = [e.strip() for e in exercises.split(",") if e.strip()]
        patient_id = pipeline.register_patient(tmp, name, ex_list or None)
        return {"patient_id": patient_id, "name": name, "assigned_exercises": ex_list}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        os.unlink(tmp)


@app.get("/patients")
async def list_patients():
    """List all registered patients with their assigned exercises."""
    return {"patients": pipeline.list_patients()}


@app.get("/patients/{patient_id}")
async def get_patient(patient_id: str):
    """Get a patient's profile including assigned exercises."""
    try:
        return pipeline.get_patient(patient_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.put("/patients/{patient_id}/exercises")
async def assign_exercises(patient_id: str, exercises: list[str]):
    """Assign (or overwrite) the rehab exercise list for a patient."""
    try:
        pipeline.assign_exercises(patient_id, exercises)
        return {"status": "updated", "patient_id": patient_id, "exercises": exercises}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── Movement Analysis ─────────────────────────────────────────────────────────

@app.post("/classify")
async def classify(
    video: UploadFile = File(...),
    track_id: int = Form(...),
    reference_dir: Optional[str] = Form(None),
    min_confidence: float = Form(0.75),
):
    """Identify which exercise a tracked person is performing."""
    tmp = _save_upload(video)
    try:
        return pipeline.classify_movement(tmp, track_id, reference_dir, min_confidence)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        os.unlink(tmp)


@app.post("/movement_context")
async def movement_context(
    video: UploadFile = File(...),
    track_id: int = Form(...),
    min_confidence: float = Form(0.75),
):
    """
    Return full OOD context for a person's movement.
    When is_ood=True, the agent uses search_hint to find a reference video,
    then calls /check_reference to verify it, then /add_exercise_reference.
    """
    tmp = _save_upload(video)
    try:
        return pipeline.get_movement_context(tmp, track_id, min_confidence=min_confidence)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        os.unlink(tmp)


@app.post("/extract_keypoints")
async def extract_keypoints(
    video: UploadFile = File(...),
    track_id: int = Form(...),
    num_frames: int = Form(32),
):
    """Extract MediaPipe pose keypoints for a specific tracked person."""
    tmp = _save_upload(video)
    try:
        return pipeline.extract_keypoints(tmp, track_id, num_frames)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        os.unlink(tmp)


@app.post("/analyze_form")
async def analyze_form(
    video: UploadFile = File(...),
    track_id: int = Form(...),
    min_confidence: float = Form(0.75),
):
    """
    classify_movement + extract_keypoints in one call.
    coaching_notes in the response is None — to be populated by the agent layer.
    """
    tmp = _save_upload(video)
    try:
        return pipeline.analyze_form(tmp, track_id, min_confidence=min_confidence)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        os.unlink(tmp)


# ── OOD / Reference Quality ───────────────────────────────────────────────────

@app.post("/check_reference")
async def check_reference(
    query_video: UploadFile = File(...),
    reference_video: UploadFile = File(...),
    query_track_id: int = Form(...),
    threshold: float = Form(0.75),
):
    """
    Test whether a downloaded video is a good reference match for a query person.
    Part of the agent OOD flow:
      1. /movement_context → is_ood=True, search_hint
      2. agent downloads candidate video
      3. /check_reference → is_good_match
      4. /add_exercise_reference if is_good_match=True
    """
    tmp_q = _save_upload(query_video)
    tmp_r = _save_upload(reference_video)
    try:
        return pipeline.check_reference_quality(tmp_q, query_track_id, tmp_r, threshold)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        os.unlink(tmp_q)
        os.unlink(tmp_r)


@app.post("/add_exercise_reference")
async def add_exercise_reference(
    video: UploadFile = File(...),
    exercise_name: str = Form(...),
):
    """
    Add a new exercise video to the reference library.
    Call after check_reference confirms is_good_match=True.
    Invalidates the reference cache so the new class is picked up immediately.
    """
    tmp = _save_upload(video)
    try:
        pipeline.add_exercise_reference(tmp, exercise_name)
        return {"status": "added", "exercise": exercise_name}
    finally:
        os.unlink(tmp)
