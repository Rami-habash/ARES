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
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import torch

from openai import OpenAI

_CV_DIR = Path(__file__).resolve().parent.parent / "CV"
if str(_CV_DIR) not in sys.path:
    sys.path.insert(0, str(_CV_DIR))

import video_embeder  # noqa: E402

from patient_profile import KAGGLE_EXERCISES, get_patient_profile  # noqa: E402

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

THRESHOLD         = 0.75
REFS_PER_EXERCISE = 5
VIDEO_ROOT        = Path(__file__).resolve().parent / "data" / "videos"
EMBED_CACHE_ROOT  = Path(__file__).resolve().parent / "data" / "embeddings"

NVIDIA_API_KEY  = os.environ.get("NVIDIA_API_KEY", "")
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
NEMOTRON_MODEL  = "nvidia/nemotron-3-nano-30b-a3b"

# ---------------------------------------------------------------------------
# S3D model singleton
# ---------------------------------------------------------------------------

_s3d_model = None

def _s3d():
    global _s3d_model
    if _s3d_model is None:
        _s3d_model = video_embeder.load_model()
    return _s3d_model


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
# Nemotron 3 Nano reasoning
# ---------------------------------------------------------------------------

def _build_ood_prompt(
    patient_exercises: list[str],
    all_scores: dict[str, float],
    already_tried: set[str],
) -> str:
    scored_lines = "\n".join(
        f"  {ex}: {score:.4f}"
        for ex, score in sorted(all_scores.items(), key=lambda x: -x[1])
    )
    untried = [e for e in KAGGLE_EXERCISES if e not in already_tried]
    catalog_str = ", ".join(untried)

    return textwrap.dedent(f"""
        A patient is performing an exercise. We tested several exercises
        against video embeddings and got these cosine similarity scores
        (threshold for a confident match = {THRESHOLD}):

        {scored_lines}

        None matched. The exercise must be one of these untested options:
        {catalog_str}

        IMPORTANT:
        - Embedding similarity is noisy. The actual exercise may have a
          completely different movement pattern from the highest-scoring
          tested exercises. Do NOT just pick exercises similar to the top
          score — consider pushing, pulling, rotation, and upper-body
          movements as well as lower-body.
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

    client = OpenAI(api_key=NVIDIA_API_KEY, base_url=NVIDIA_BASE_URL)
    logger.debug("Calling Nemotron 3 Nano for OOD candidate selection...")

    response = client.chat.completions.create(
        model=NEMOTRON_MODEL,
        # System message disables Nemotron's reasoning mode so the model
        # commits to a direct answer instead of spinning in circles.
        messages=[
            {"role": "system", "content": "detailed thinking off"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        max_tokens=1024,
    )
    msg = response.choices[0].message
    raw = msg.content or getattr(msg, "reasoning_content", None) or ""
    logger.info("Nemotron raw reply: %s", raw)

    # Find all bracketed candidates; try them from longest to shortest so we
    # prefer the full answer array over any incidental list-like fragments.
    matches = sorted(re.findall(r"\[[^\[\]]*\]", raw, re.DOTALL), key=len, reverse=True)
    for m in matches:
        try:
            candidates = json.loads(m)
        except json.JSONDecodeError:
            continue
        if isinstance(candidates, list):
            return [c for c in candidates if isinstance(c, str)]
    logger.warning("Nemotron reply contained no parseable JSON array.")
    return []


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

@dataclass
class IdentifyResult:
    """Outcome of one identification pass.

    `exercise` is set only when `best_score >= THRESHOLD`. `best_guess` and
    `best_score` are always populated when at least one candidate was scored,
    so the UI can surface the leading candidate even if it didn't clear the
    bar.
    """
    exercise:   str | None
    best_guess: str | None = None
    best_score: float | None = None
    all_scores: dict[str, float] = field(default_factory=dict)


def identify_exercise(patient_id: str, query_video_path: str) -> IdentifyResult:
    """Identify the exercise being performed in *query_video_path*.

    Returns an IdentifyResult. `exercise` is the matched name, or None when
    nothing cleared the confidence threshold — but `best_guess` always
    reflects the top-scoring candidate so the caller can surface it.
    """
    profile = get_patient_profile(patient_id)
    if profile is None:
        raise ValueError(f"Unknown patient id: {patient_id!r}")

    kaggle_catalog = list(KAGGLE_EXERCISES)
    already_tried: set[str] = set(profile.exercises)

    logger.info("[%s] Embedding query video...", patient_id)
    query_emb = _embed(Path(query_video_path))

    # ── 1. In-domain pass ────────────────────────────────────────────────────
    in_domain = _available_exercises(profile.exercises)
    logger.info(
        "[%s] In-domain pass: scoring %d prescribed exercises.",
        patient_id, len(in_domain),
    )

    all_scores = _score_exercises(query_emb, in_domain)

    if all_scores:
        best_ex = max(all_scores, key=lambda k: all_scores[k])
        best_score = all_scores[best_ex]
        if best_score >= THRESHOLD:
            logger.info("[%s] In-domain match: %r (%.4f)", patient_id, best_ex, best_score)
            return IdentifyResult(
                exercise=best_ex, best_guess=best_ex, best_score=best_score,
                all_scores=dict(all_scores),
            )
        logger.info(
            "[%s] No in-domain match (best=%s %.4f). Entering OOD loop.",
            patient_id, best_ex, best_score,
        )
    else:
        logger.info("[%s] No in-domain reference videos. Going straight to OOD.", patient_id)

    # ── 2. OOD reasoning loop ────────────────────────────────────────────────
    round_num = 0
    while True:
        round_num += 1
        logger.info("[%s] OOD round %d", patient_id, round_num)

        prompt = _build_ood_prompt(
            patient_exercises=profile.exercises,
            all_scores=all_scores,
            already_tried=already_tried,
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
            best_ex = max(round_scores, key=lambda k: round_scores[k])
            best_score = round_scores[best_ex]
            if best_score >= THRESHOLD:
                logger.info("[%s] OOD match: %r (%.4f)", patient_id, best_ex, best_score)
                return IdentifyResult(
                    exercise=best_ex, best_guess=best_ex, best_score=best_score,
                    all_scores=dict(all_scores),
                )
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
    top_guess  = all_scores_sorted[0][0] if all_scores_sorted else None
    top_score  = all_scores_sorted[0][1] if all_scores_sorted else None
    return IdentifyResult(
        exercise=None, best_guess=top_guess, best_score=top_score,
        all_scores=dict(all_scores),
    )
