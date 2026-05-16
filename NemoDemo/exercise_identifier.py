"""Exercise identification — hooks the CV pipeline to the patient profile store.

Flow
----
1. In-domain pass
   Call pipeline.classify_movement with the patient's prescribed exercises as
   the only reference videos on disk.  If it returns a prediction (score ≥ 0.75),
   return that exercise name immediately.

2. Out-of-domain (OOD) loop
   Call pipeline.get_movement_context to get the full similarity scores.
   Pass them to Nemotron 3 Nano, which reasons about which untested catalog
   exercises to try next.  For each candidate batch, temporarily copy the
   candidate videos into the reference dir so pipeline.classify_movement can
   score them.  Repeat until a match is found.

   The exercise is guaranteed to exist in the Kaggle catalog, so the loop
   terminates with a match once the right exercise is reached.

Reference video layout (NemoDemo/data/videos/)
----------------------------------------------
Only the 11 exercises assigned across all patient profiles have folders here.
The remaining 11 catalog exercises have no videos — that absence is what
triggers the OOD path when a patient does something outside their prescription.
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
import textwrap
from pathlib import Path

from openai import OpenAI

# CV pipeline lives one level up in CV/
_CV_DIR = Path(__file__).resolve().parent.parent / "CV"
if str(_CV_DIR) not in sys.path:
    sys.path.insert(0, str(_CV_DIR))

import pipeline  # noqa: E402 — CV pipeline

from patient_profile import KAGGLE_EXERCISES, get_patient_profile  # noqa: E402

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

THRESHOLD    = 0.75
VIDEO_ROOT   = Path(__file__).resolve().parent / "data" / "videos"

NVIDIA_API_KEY  = os.environ.get("NVIDIA_API_KEY", "")
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
NEMOTRON_MODEL  = "nvidia/nemotron-3-nano-30b-a3b"

# ---------------------------------------------------------------------------
# Reference dir helpers
# ---------------------------------------------------------------------------

def _exercise_has_videos(exercise_name: str) -> bool:
    folder = VIDEO_ROOT / exercise_name
    return folder.is_dir() and any(folder.iterdir())


def _available_exercises(names: list[str]) -> list[str]:
    """Filter to exercises that actually have reference videos on disk."""
    return [n for n in names if _exercise_has_videos(n)]


# ---------------------------------------------------------------------------
# Nemotron 3 Nano reasoning
# ---------------------------------------------------------------------------

def _build_ood_prompt(
    patient_exercises: list[str],
    all_scores: dict[str, float],
    already_tried: set[str],
) -> str:
    scored_lines = "\n".join(
        f"  {ex}: {score:.4f}" for ex, score in sorted(all_scores.items(), key=lambda x: -x[1])
    )
    untried = [e for e in KAGGLE_EXERCISES if e not in already_tried]
    catalog_lines = "\n".join(f"  - {e}" for e in untried)

    return textwrap.dedent(f"""
        You are an expert exercise-recognition reasoning engine.

        A patient is performing a physical motion that could not be confidently
        matched to any reference video. The cosine similarity threshold for a
        confident match is {THRESHOLD}.

        The exercise MUST be one of the exercises in the untested catalog list
        below — it is guaranteed to be there.

        ## Patient's prescribed exercises
        {', '.join(patient_exercises)}

        ## Similarity scores collected so far (higher = more similar)
        {scored_lines}

        ## Exercises in the catalog not yet tested
        {catalog_lines}

        ## Your task
        Think step-by-step:

        1. Examine which exercises scored highest and identify their shared
           movement patterns (e.g. leg drive, hip hinge, pushing, pulling,
           rotation, isometric hold, knee flexion, shoulder abduction).
        2. Consider which untested catalog exercises share those movement
           characteristics and could explain the observed similarity pattern.
        3. Think about biomechanical relationships: exercises that recruit the
           same muscle groups or share the same joint actions tend to produce
           similar embeddings.
        4. Rank the untested exercises from most to least likely to match.
        5. Select up to 5 candidates to test next — prioritize exercises most
           likely to cross the {THRESHOLD} threshold.

        Respond ONLY with a JSON array of exercise names (strings) from the
        untested catalog list, ordered by priority.  Example:
        ["squat", "leg press", "romanian deadlift"]

        Do not include already-tested exercises. Do not add any commentary
        outside the JSON array.
    """).strip()


def _ask_nemotron(prompt: str) -> list[str]:
    import json, re

    client = OpenAI(api_key=NVIDIA_API_KEY, base_url=NVIDIA_BASE_URL)
    logger.debug("Calling Nemotron 3 Nano for OOD candidate selection...")

    response = client.chat.completions.create(
        model=NEMOTRON_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=512,
    )
    raw = response.choices[0].message.content or ""
    logger.debug("Nemotron reply: %s", raw)

    match = re.search(r"\[.*?\]", raw, re.DOTALL)
    if not match:
        logger.warning("Nemotron reply contained no JSON array.")
        return []
    try:
        candidates = json.loads(match.group())
        if not isinstance(candidates, list):
            return []
        return [c for c in candidates if isinstance(c, str)]
    except json.JSONDecodeError:
        logger.warning("Failed to parse Nemotron JSON reply.")
        return []


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def identify_exercise(patient_id: str, query_video_path: str, track_id: int) -> str | None:
    """Identify the exercise being performed in *query_video_path*.

    track_id must come from pipeline.scan_persons called on the same video
    immediately before this function.

    Returns the matched exercise name, or None only if reference videos are
    missing for all candidates (should not happen in a properly seeded setup).
    """
    profile = get_patient_profile(patient_id)
    if profile is None:
        raise ValueError(f"Unknown patient id: {patient_id!r}")

    kaggle_catalog = list(KAGGLE_EXERCISES)
    already_tried: set[str] = set(profile.exercises)

    # ── 1. In-domain pass ────────────────────────────────────────────────────
    # Only score exercises that are both prescribed and have reference videos.
    in_domain = _available_exercises(profile.exercises)
    logger.info(
        "[%s] In-domain pass: %d / %d prescribed exercises have reference videos.",
        patient_id, len(in_domain), len(profile.exercises),
    )

    if in_domain:
        result = pipeline.classify_movement(
            query_video_path,
            track_id=track_id,
            reference_dir=str(VIDEO_ROOT),
            min_confidence=THRESHOLD,
        )
        # classify_movement scores all exercises in VIDEO_ROOT; filter to patient's
        all_scores: dict[str, float] = {
            k: v for k, v in result["all_scores"].items() if k in profile.exercises
        }

        if result["prediction"] in profile.exercises:
            logger.info(
                "[%s] In-domain match: %r (%.4f)",
                patient_id, result["prediction"], result["confidence"],
            )
            return result["prediction"]

        best_score = max(all_scores.values()) if all_scores else 0.0
        logger.info(
            "[%s] No in-domain match (best=%.4f). Entering OOD reasoning loop.",
            patient_id, best_score,
        )
    else:
        logger.info("[%s] No in-domain reference videos found. Going straight to OOD.", patient_id)
        all_scores = {}

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

        # Filter to candidates that actually have videos on disk.
        testable = _available_exercises(valid_candidates)
        already_tried.update(valid_candidates)

        if not testable:
            logger.info("[%s] Candidates have no reference videos, skipping round.", patient_id)
            continue

        logger.info("[%s] Testing: %s", patient_id, testable)

        # Stage: temporarily copy candidate videos into a scratch dir so
        # classify_movement can score all of them in one pass without
        # interfering with the permanent reference library.
        scratch = VIDEO_ROOT.parent / "_ood_scratch"
        try:
            scratch.mkdir(parents=True, exist_ok=True)
            for ex in testable:
                shutil.copytree(VIDEO_ROOT / ex, scratch / ex, dirs_exist_ok=True)

            result = pipeline.classify_movement(
                query_video_path,
                track_id=track_id,
                reference_dir=str(scratch),
                min_confidence=THRESHOLD,
            )
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
            pipeline._ref_cache = None  # invalidate cache after scratch dir is gone

        round_scores = {k: v for k, v in result["all_scores"].items() if k in testable}
        all_scores.update(round_scores)

        if result["prediction"] in testable:
            logger.info(
                "[%s] OOD match: %r (%.4f)", patient_id, result["prediction"], result["confidence"]
            )
            return result["prediction"]

        best = max(round_scores.values()) if round_scores else 0.0
        logger.info(
            "[%s] Round %d best: %.4f — continuing.", patient_id, round_num, best
        )

    # All candidates exhausted without a match.
    all_scores_sorted = sorted(all_scores.items(), key=lambda x: -x[1])
    logger.error(
        "[%s] Identification failed. Full score table:\n%s",
        patient_id,
        "\n".join(f"  {ex}: {score:.4f}" for ex, score in all_scores_sorted),
    )
    return None
