"""Exercise identification — hooks the CV pipeline to the patient profile store.

Flow
----
1. Embed the query video with S3D (full frame, no YOLO person crop needed).
2. In-domain pass: compare against up to REFS_PER_EXERCISE reference videos
   for each of the patient's prescribed exercises.  If the best mean cosine
   similarity score is >= THRESHOLD, return that exercise name immediately.
3. OOD loop: pass all scores so far to Nemotron 3 Nano, which reasons about
   which untested catalog exercises to try next.  Score those candidates.
   Repeat until a match is found (the exercise is guaranteed to be in the
   Kaggle catalog).

Why no YOLO / track_id
-----------------------
pipeline.classify_movement crops the query person using YOLO track IDs.
Track IDs are only stable within a single YOLO tracker session — calling
track() twice on the same video produces different IDs each time.  For
exercise identification we only need the motion pattern, not person isolation,
so we embed the full video frame directly with video_embeder.embed().

Reference video layout (NemoDemo/data/videos/)
----------------------------------------------
Only the 11 exercises assigned across all patient profiles have folders here.
The remaining 11 catalog exercises have no videos — that absence is what
triggers the OOD path when a patient does something outside their prescription.

Embedding cache
---------------
Reference embeddings are cached as .pt files under data/embeddings/ so
subsequent runs are near-instant for already-seen videos.
"""

from __future__ import annotations

import logging
import os
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch

import subprocess

_CV_DIR = Path(__file__).resolve().parent.parent / "CV"
if str(_CV_DIR) not in sys.path:
    sys.path.insert(0, str(_CV_DIR))

import video_embeder  # noqa: E402
import keypoint_extraction  # noqa: E402
import form_analysis  # noqa: E402

from patient_profile import KAGGLE_EXERCISES, get_patient_profile  # noqa: E402

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

THRESHOLD         = 0.75
REFS_PER_EXERCISE = 5
# Weight of the pose-fingerprint score in the blended similarity. The remainder
# (1 - POSE_WEIGHT) is the S3D embedding score. Pose dominates because S3D on
# short uncontrolled clips is noisy; the keypoint signature (which joints moved
# and by how much) is much more discriminating of WHICH exercise was performed.
POSE_WEIGHT       = 0.7
# Minimum number of visible joint groups (out of 5) required to even attempt
# identification. Below this, the camera isn't seeing enough of the body to
# distinguish exercises — surface "insufficient view" instead of guessing.
MIN_VISIBLE_GROUPS = 2
# Hard cap on OOD reasoning rounds per tick. Each round = 1 Nemotron call
# (~5–10s) + scoring candidates, so without a cap a single misidentified
# clip can lock the daemon up for minutes. The frontend broadcasts
# best_guess/thinking only between ticks, so a long tick = a dead UI.
MAX_OOD_ROUNDS    = 4
VIDEO_ROOT        = Path(__file__).resolve().parent / "data" / "videos"
EMBED_CACHE_ROOT  = Path(__file__).resolve().parent / "data" / "embeddings"

OPENCLAW_SANDBOX    = "nemo"
OPENCLAW_OOD_SESSION = "+10000000002"  # separate key from coaching so OOD queries don't bleed into coaching context

# ---------------------------------------------------------------------------
# S3D model singleton
# ---------------------------------------------------------------------------

_s3d_model = None

def _s3d():
    global _s3d_model
    if _s3d_model is None:
        _s3d_model = video_embeder.load_model()
    return _s3d_model


_pose_model_singleton = None

def _pose_model():
    """Lazy MediaPipe pose model for movement summaries."""
    global _pose_model_singleton
    if _pose_model_singleton is None:
        _pose_model_singleton = keypoint_extraction.load_model()
    return _pose_model_singleton


# ---------------------------------------------------------------------------
# Embedding helpers (with disk cache)
# ---------------------------------------------------------------------------

def _cache_path(video_path: Path) -> Path:
    try:
        rel = video_path.relative_to(VIDEO_ROOT)
    except ValueError:
        rel = Path(video_path.name)
    return EMBED_CACHE_ROOT / rel.parent / (rel.stem + ".pt")


def _embed(video_path: Path) -> np.ndarray:
    """S3D embed a video, reading from disk cache if available."""
    cache = _cache_path(video_path)
    if cache.exists():
        return torch.load(cache, weights_only=True).numpy()
    emb = video_embeder.embed(_s3d(), str(video_path))
    cache.parent.mkdir(parents=True, exist_ok=True)
    torch.save(torch.from_numpy(emb), cache)
    return emb


# ---------------------------------------------------------------------------
# Pose fingerprint — primary signal for exercise identification.
#
# A fingerprint is a 10-dim vector: 5 range_deg values + 5 mean_deg values,
# one each for knees / hips / elbows / shoulders / ankles (left+right merged).
# Range captures WHICH joints moved; mean captures posture (standing vs bent,
# arms up vs down). Together these distinguish e.g. squat (knees+hips+ankles
# moving, mid-range means) from leg extension (only knees moving, hip near 180°).
#
# Visibility is tracked per dimension: a joint group with no visible frames
# gets NaN in both range and mean, and is masked out of similarity computations
# rather than being compared as zero (which would falsely look like agreement
# with another static-on-that-joint reference).
# ---------------------------------------------------------------------------

_FINGERPRINT_GROUPS: list[tuple[str, list[str]]] = [
    ("knees",     ["left_knee",     "right_knee"]),
    ("hips",      ["left_hip",      "right_hip"]),
    ("elbows",    ["left_elbow",    "right_elbow"]),
    ("shoulders", ["left_shoulder", "right_shoulder"]),
    ("ankles",    ["left_ankle",    "right_ankle"]),
]

# Tolerances used to convert raw angle differences into a [0, 1] similarity.
# A range diff of RANGE_TOL° (or a mean diff of MEAN_TOL°) drops that
# dimension's similarity to 0.5; double that → ~0. Tuned so squat vs leg
# extension (knee range ~80° vs ~80°, hip range ~60° vs ~5°) lands at a
# meaningfully different score.
_RANGE_TOL_DEG = 30.0
_MEAN_TOL_DEG  = 40.0


def _pose_cache_path(video_path: Path) -> Path:
    try:
        rel = video_path.relative_to(VIDEO_ROOT)
    except ValueError:
        rel = Path(video_path.name)
    return EMBED_CACHE_ROOT / rel.parent / (rel.stem + ".pose.npy")


def _group_range_and_mean(
    joint_angles: dict[str, list[float]], names: list[str]
) -> tuple[float, float]:
    """Aggregate left/right joint angles into (range_deg, mean_deg).
    Returns (nan, nan) if no visible frames across either joint."""
    vals: list[float] = []
    for joint in names:
        for v in joint_angles.get(joint, []):
            if v == v:  # not nan
                vals.append(v)
    if not vals:
        return float("nan"), float("nan")
    return max(vals) - min(vals), sum(vals) / len(vals)


def _compute_fingerprint(video_path: Path) -> np.ndarray:
    """10-dim pose fingerprint: 5 ranges + 5 means. NaN where not visible."""
    try:
        landmarks_seq = form_analysis.extract_reference_keypoints(
            _pose_model(), str(video_path), bbox_model=None, num_frames=24,
        )
        if not any(landmarks_seq):
            return np.full(10, np.nan, dtype=np.float32)
        joint_angles = form_analysis.compute_joint_angles(landmarks_seq)
    except Exception as exc:
        logger.warning("Pose fingerprint failed for %s: %s", video_path.name, exc)
        return np.full(10, np.nan, dtype=np.float32)

    ranges: list[float] = []
    means:  list[float] = []
    for _, names in _FINGERPRINT_GROUPS:
        r, m = _group_range_and_mean(joint_angles, names)
        ranges.append(r)
        means.append(m)
    return np.array(ranges + means, dtype=np.float32)


def _fingerprint(video_path: Path) -> np.ndarray:
    """Pose fingerprint with disk cache, mirroring _embed()."""
    cache = _pose_cache_path(video_path)
    if cache.exists():
        return np.load(cache)
    fp = _compute_fingerprint(video_path)
    cache.parent.mkdir(parents=True, exist_ok=True)
    np.save(cache, fp)
    return fp


def _visible_group_count(fingerprint: np.ndarray) -> int:
    """How many of the 5 joint groups have a usable (non-NaN) range value."""
    return int(np.sum(~np.isnan(fingerprint[:5])))


def _pose_similarity(query_fp: np.ndarray, ref_fp: np.ndarray) -> float:
    """Visibility-masked similarity in [0, 1] between two fingerprints.

    Each of the 10 dims contributes only if BOTH vectors have a non-NaN value
    there. Per-dim similarity decays exponentially with the absolute angle
    diff against the tolerance for that dim type (range vs mean). Returns NaN
    if no dimensions overlap at all (e.g. query saw legs, ref saw arms only)."""
    tols = np.array([_RANGE_TOL_DEG] * 5 + [_MEAN_TOL_DEG] * 5, dtype=np.float32)
    valid = ~(np.isnan(query_fp) | np.isnan(ref_fp))
    if not valid.any():
        return float("nan")
    diff = np.abs(query_fp[valid] - ref_fp[valid])
    sims = np.exp(-diff / tols[valid])  # 0° → 1.0, tol° → ~0.37, 2*tol° → ~0.14
    return float(np.mean(sims))


def _exercise_has_videos(exercise_name: str) -> bool:
    folder = VIDEO_ROOT / exercise_name
    return folder.is_dir() and any(folder.iterdir())


def _available_exercises(names: list[str]) -> list[str]:
    return [n for n in names if _exercise_has_videos(n)]


def _sample_reference_videos(exercise_name: str) -> list[Path]:
    """Return up to REFS_PER_EXERCISE .mp4s, preferring already-cached embeds."""
    folder = VIDEO_ROOT / exercise_name
    if not folder.is_dir():
        return []
    all_mp4s = sorted(f for f in folder.iterdir() if f.suffix.lower() == ".mp4")
    if not all_mp4s:
        return []
    cached = [vf for vf in all_mp4s if _cache_path(vf).exists()]
    pool = cached + [f for f in all_mp4s if f not in cached]
    return pool[:REFS_PER_EXERCISE]


def _score_exercises(query_emb: np.ndarray, exercises: list[str]) -> dict[str, float]:
    """Cosine similarity between query and the mean embedding for each exercise."""
    scores: dict[str, float] = {}
    for ex in exercises:
        vids = _sample_reference_videos(ex)
        if not vids:
            continue
        ref_embs = np.stack([_embed(vf) for vf in vids])
        score = float(np.mean(ref_embs @ query_emb))
        scores[ex] = round(score, 4)
        logger.debug("  %s → %.4f  (%d refs)", ex, score, len(vids))
    return scores


# ---------------------------------------------------------------------------
# Movement summary — gives Nemotron actual signal about WHAT the patient did
# instead of just a column of cosine-similarity scores.
# ---------------------------------------------------------------------------

# Joints to summarise + their human-readable group. Pairs are described together
# (the left/right means usually move in lockstep for symmetric exercises).
_JOINT_GROUPS: list[tuple[str, list[str]]] = [
    ("knees",     ["left_knee",     "right_knee"]),
    ("hips",      ["left_hip",      "right_hip"]),
    ("elbows",    ["left_elbow",    "right_elbow"]),
    ("shoulders", ["left_shoulder", "right_shoulder"]),
    ("ankles",    ["left_ankle",    "right_ankle"]),
]

# A joint counts as "moving" when its angle range over the clip exceeds this.
_MOVEMENT_DEG_THRESHOLD = 15.0
# Frames with this fraction of NaN angles are skipped when computing the range.
_MIN_VISIBLE_FRAMES_RATIO = 0.25


def _group_movement(joint_angles: dict[str, list[float]], names: list[str]) -> dict:
    """Aggregate left/right joint pair into one row. Returns visibility + range."""
    all_vals: list[float] = []
    for joint in names:
        for v in joint_angles.get(joint, []):
            if v == v:  # not nan
                all_vals.append(v)
    if not all_vals:
        return {"visible": False, "range_deg": 0.0, "mean_deg": 0.0}
    return {
        "visible":   True,
        "range_deg": max(all_vals) - min(all_vals),
        "mean_deg":  sum(all_vals) / len(all_vals),
        "n_samples": len(all_vals),
    }


def summarize_movement(clip_path: str) -> str:
    """Return a 1-line description of which joints moved and by how much.

    Used in the OOD prompt so the LLM has actual movement context, not just
    a score table. Quietly returns "Movement summary unavailable" on any
    extraction error — never raises.
    """
    try:
        landmarks_seq = form_analysis.extract_reference_keypoints(
            _pose_model(), clip_path, bbox_model=None, num_frames=24,
        )
        if not any(landmarks_seq):
            return "Movement summary: no pose detected (subject likely out of frame)."

        joint_angles = form_analysis.compute_joint_angles(landmarks_seq)

        # Visibility per group → tells the LLM what we COULDN'T see.
        moving_groups:  list[str] = []
        static_groups:  list[str] = []
        hidden_groups:  list[str] = []
        for label, names in _JOINT_GROUPS:
            agg = _group_movement(joint_angles, names)
            if not agg["visible"]:
                hidden_groups.append(label)
                continue
            if agg["range_deg"] >= _MOVEMENT_DEG_THRESHOLD:
                moving_groups.append(f"{label} (~{int(agg['range_deg'])}° range)")
            else:
                static_groups.append(f"{label} (~{int(agg['mean_deg'])}°, ±{int(agg['range_deg'])}°)")

        parts: list[str] = []
        if moving_groups:
            parts.append("Moving: " + ", ".join(moving_groups))
        else:
            parts.append("No joints moved meaningfully.")
        if static_groups:
            parts.append("Static: " + ", ".join(static_groups))
        if hidden_groups:
            parts.append("Not visible: " + ", ".join(hidden_groups))
        return "Movement summary — " + " | ".join(parts)
    except Exception as exc:
        logger.warning("Movement summary failed: %s", exc)
        return "Movement summary unavailable."


# ---------------------------------------------------------------------------
# Nemotron 3 Nano reasoning
# ---------------------------------------------------------------------------

def _build_ood_prompt(
    patient_exercises: list[str],
    all_scores: dict[str, float],
    already_tried: set[str],
    movement_summary: str = "",
) -> str:
    scored_lines = "\n".join(
        f"  {ex}: {score:.4f}"
        for ex, score in sorted(all_scores.items(), key=lambda x: -x[1])
    )
    untried = [e for e in KAGGLE_EXERCISES if e not in already_tried]
    catalog_str = ", ".join(untried)

    movement_block = (
        f"\n        Pose evidence from MediaPipe (joint angle ranges over the clip):\n"
        f"        {movement_summary}\n"
        if movement_summary else ""
    )

    return textwrap.dedent(f"""
        A patient is performing an exercise. We tested several exercises
        against video embeddings and got these cosine similarity scores
        (threshold for a confident match = {THRESHOLD}):

        {scored_lines}
        {movement_block}
        None matched. The exercise must be one of these untested options:
        {catalog_str}

        IMPORTANT:
        - Use the pose evidence above as your PRIMARY signal — the embedding
          scores are noisy. If knees + hips show large range and shoulders
          are static, prefer lower-body exercises (squat, lunge variations,
          deadlift). If shoulders + elbows show large range and lower body
          is static, prefer upper-body exercises (push-up, shoulder press,
          row variations). If "Not visible" lists the lower body, do NOT
          suggest lower-body-dominant exercises.
        - Cover a diverse range of movement patterns in your picks.

        Output a JSON array of exactly 5 exercise names from the untested
        list above, ordered by your best guess of likelihood. Example
        output format (do NOT include this exact answer, this is just
        a format example):

        ["push-up", "pull up", "deadlift", "russian twist", "lateral raise"]

        Output ONLY the JSON array. No preamble, no explanation.
    """).strip()


def _ask_nemotron(prompt: str) -> list[str]:
    import json, re

    logger.debug("Calling nemo via openclaw for OOD candidate selection...")
    # openshell sandbox exec rejects newlines in CLI args, so flatten the
    # prompt to a single line. Collapse all whitespace runs to single spaces.
    flat_prompt = re.sub(r"\s+", " ", prompt).strip()
    cmd = [
        "openshell", "-g", "nemoclaw",
        "sandbox", "exec", "-n", OPENCLAW_SANDBOX, "--",
        "openclaw", "agent",
        "--to", OPENCLAW_OOD_SESSION,
        "--message", flat_prompt,
        "--json",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except Exception as exc:
        logger.warning("openclaw OOD call failed: %s", exc)
        return []

    if proc.returncode != 0:
        logger.warning("openclaw OOD exited %d: %s", proc.returncode, proc.stderr[:200])
        return []

    try:
        data = json.loads(proc.stdout)
        raw = data.get("result", {}).get("payloads", [{}])[0].get("text", "")
    except Exception:
        logger.warning("Could not parse openclaw OOD response: %s", proc.stdout[:200])
        return []

    logger.info("Nemotron OOD reply: %s", raw)

    # Nemotron sometimes line-wraps inside a JSON string (e.g. "push\n-up"),
    # which makes json.loads choke even though the intent is obviously
    # "push-up". Strip raw line breaks before parsing — JSON strings don't
    # permit them, so this can't damage a well-formed reply.
    cleaned = raw.replace("\r", "").replace("\n", "")

    # Find all bracketed candidates; try them from longest to shortest so we
    # prefer the full answer array over any incidental list-like fragments.
    matches = sorted(re.findall(r"\[[^\[\]]*\]", cleaned, re.DOTALL), key=len, reverse=True)
    for m in matches:
        try:
            candidates = json.loads(m)
        except json.JSONDecodeError:
            continue
        if isinstance(candidates, list):
            return [c for c in candidates if isinstance(c, str)]
    logger.warning("Nemotron OOD reply contained no parseable JSON array.")
    return []


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

@dataclass
class IdentifyResult:
    """Outcome of one identify_exercise() call.

    `exercise` is the confirmed match (only set when best_score >= THRESHOLD).
    `best_guess`/`best_score` always hold the leading candidate so the UI can
    render a live "best guess" even before the threshold is cleared.
    """
    exercise:   str | None
    best_guess: str | None
    best_score: float | None


def _top_score(scores: dict[str, float]) -> tuple[str | None, float | None]:
    if not scores:
        return None, None
    name = max(scores, key=lambda k: scores[k])
    return name, scores[name]


def identify_exercise(patient_id: str, query_video_path: str) -> IdentifyResult:
    """Identify the exercise being performed in *query_video_path*.

    Always returns an IdentifyResult. `exercise` is None when no candidate
    cleared THRESHOLD; `best_guess`/`best_score` still carry the top scorer
    so callers can show partial-match feedback.
    """
    profile = get_patient_profile(patient_id)
    if profile is None:
        raise ValueError(f"Unknown patient id: {patient_id!r}")

    kaggle_catalog = list(KAGGLE_EXERCISES)
    already_tried: set[str] = set(profile.exercises)

    logger.info("[%s] Embedding query video...", patient_id)
    query_emb = _embed(Path(query_video_path))

    # Pose summary gives the OOD reasoner real movement signal — without it
    # the LLM only sees a score table and tends to give canned answers.
    movement_summary = summarize_movement(query_video_path)
    logger.info("[%s] %s", patient_id, movement_summary)

    # ── 1. In-domain pass ────────────────────────────────────────────────────
    in_domain = _available_exercises(profile.exercises)
    logger.info(
        "[%s] In-domain pass: scoring %d prescribed exercises.",
        patient_id, len(in_domain),
    )

    all_scores = _score_exercises(query_emb, in_domain)

    if all_scores:
        best_ex, best_score = _top_score(all_scores)
        if best_score is not None and best_score >= THRESHOLD:
            logger.info("[%s] In-domain match: %r (%.4f)", patient_id, best_ex, best_score)
            return IdentifyResult(exercise=best_ex, best_guess=best_ex, best_score=best_score)
        logger.info(
            "[%s] No in-domain match (best=%s %.4f). Entering OOD loop.",
            patient_id, best_ex, best_score,
        )
    else:
        logger.info("[%s] No in-domain reference videos. Going straight to OOD.", patient_id)

    # ── 2. OOD reasoning loop ────────────────────────────────────────────────
    round_num = 0
    while round_num < MAX_OOD_ROUNDS:
        round_num += 1
        logger.info("[%s] OOD round %d/%d", patient_id, round_num, MAX_OOD_ROUNDS)

        prompt = _build_ood_prompt(
            patient_exercises=profile.exercises,
            all_scores=all_scores,
            already_tried=already_tried,
            movement_summary=movement_summary,
        )
        candidates = _ask_nemotron(prompt)

        valid_candidates = [
            c for c in candidates
            if c in kaggle_catalog and c not in already_tried
        ]
        if not valid_candidates:
            logger.info("[%s] No new valid candidates. Stopping.", patient_id)
            break

        testable = _available_exercises(valid_candidates)
        already_tried.update(valid_candidates)

        if not testable:
            logger.info("[%s] Candidates have no reference videos, skipping round.", patient_id)
            continue

        logger.info("[%s] Testing: %s", patient_id, testable)
        round_scores = _score_exercises(query_emb, testable)
        all_scores.update(round_scores)

        if round_scores:
            best_ex, best_score = _top_score(round_scores)
            if best_score is not None and best_score >= THRESHOLD:
                logger.info("[%s] OOD match: %r (%.4f)", patient_id, best_ex, best_score)
                return IdentifyResult(exercise=best_ex, best_guess=best_ex, best_score=best_score)
            logger.info(
                "[%s] Round %d best: %s=%.4f — continuing.",
                patient_id, round_num, best_ex, best_score,
            )

    all_scores_sorted = sorted(all_scores.items(), key=lambda x: -x[1])
    logger.error(
        "[%s] Identification failed. Full score table:\n%s",
        patient_id,
        "\n".join(f"  {ex}: {score:.4f}" for ex, score in all_scores_sorted),
    )
    overall_best, overall_score = _top_score(all_scores)
    return IdentifyResult(exercise=None, best_guess=overall_best, best_score=overall_score)
