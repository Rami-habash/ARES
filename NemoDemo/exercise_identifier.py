"""Exercise identification via cosine-similarity embeddings + Nemotron 3 Nano reasoning.

Flow
----
1. In-domain pass
   Score every reference video assigned to the patient (from their profile).
   If any video scores >= THRESHOLD, return that exercise name immediately.

2. Out-of-domain (OOD) loop
   Pass the accumulated scores to Nemotron 3 Nano and ask it to reason about
   which untested catalog exercises to try next.
   Score those candidates.  If a hit is found, return it.
   Repeat until the model returns no new candidates (the exercise is always in
   the Kaggle catalog, so this loop will terminate with a match).

Similarity API contract (caller-provided)
------------------------------------------
The `similarity_fn` argument must be a callable:

    similarity_fn(query_video_path: str, reference_video_path: str) -> float

It returns a cosine-similarity score in [0, 1].  The implementation (embedding
model, transport, caching) is managed externally — this module only calls it.

Video layout on disk
---------------------
    NemoDemo/data/videos/<exercise_name>/<any_name>.mp4

The first .mp4 found in the exercise folder is used as the reference.
"""

from __future__ import annotations

import glob
import logging
import os
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from openai import OpenAI  # NVIDIA NIM endpoint is OpenAI-compatible

from patient_profile import KAGGLE_EXERCISES, get_patient_profile

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

THRESHOLD = 0.75

NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "")
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
NEMOTRON_MODEL = "nvidia/nemotron-3-nano-30b-a3b"

VIDEO_ROOT = Path(__file__).resolve().parent / "data" / "videos"

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

SimilarityFn = Callable[[str, str], float]


@dataclass
class _Score:
    exercise: str
    video_path: str
    score: float


def _reference_video(exercise_name: str) -> str | None:
    """Return path to the first .mp4 in the exercise's video folder, or None."""
    folder = VIDEO_ROOT / exercise_name
    hits = glob.glob(str(folder / "*.mp4"))
    return hits[0] if hits else None


def _score_exercises(
    query_path: str,
    exercise_names: list[str],
    similarity_fn: SimilarityFn,
) -> list[_Score]:
    """Score a list of exercise names against the query video. Skips missing videos."""
    results: list[_Score] = []
    for name in exercise_names:
        ref = _reference_video(name)
        if ref is None:
            logger.debug("No reference video for %r, skipping.", name)
            continue
        score = similarity_fn(query_path, ref)
        logger.debug("  %s → %.4f", name, score)
        results.append(_Score(exercise=name, video_path=ref, score=score))
    return sorted(results, key=lambda s: s.score, reverse=True)


def _best(scores: list[_Score]) -> _Score | None:
    return scores[0] if scores else None


# ---------------------------------------------------------------------------
# Nemotron 3 Nano reasoning
# ---------------------------------------------------------------------------

def _build_ood_prompt(
    patient_exercises: list[str],
    all_scores_so_far: list[_Score],
    already_tried: set[str],
    kaggle_catalog: list[str],
) -> str:
    scored_lines = "\n".join(
        f"  {s.exercise}: {s.score:.4f}" for s in all_scores_so_far
    )
    untried = [e for e in kaggle_catalog if e not in already_tried]
    catalog_lines = "\n".join(f"  - {e}" for e in untried)

    return textwrap.dedent(f"""
        You are an expert exercise-recognition reasoning engine.

        A patient is performing a physical motion that could not be confidently
        matched to any of their prescribed exercises. The cosine similarity
        threshold for a confident match is {THRESHOLD}.

        The exercise the patient is performing MUST be one of the exercises in
        the untested catalog list below — it is guaranteed to be there.

        ## Patient's prescribed exercises
        {', '.join(patient_exercises)}

        ## Similarity scores collected so far (higher = more similar)
        {scored_lines}

        ## Exercises in the catalog not yet tested
        {catalog_lines}

        ## Your task
        Think step-by-step about what the patient might be doing:

        1. Look at which exercises scored highest and what movement patterns
           they share (e.g., leg drive, hip hinge, pushing, pulling, rotation,
           isometric hold).
        2. Consider which untested catalog exercises share those movement
           characteristics and could explain the observed similarity pattern.
        3. Think about biomechanical relationships: exercises that recruit the
           same muscle groups or share the same joint actions tend to produce
           similar embeddings.
        4. Rank the untested exercises from most to least likely to match.
        5. Select up to 5 candidates to test next — prioritize exercises that
           are most likely to cross the {THRESHOLD} threshold.

        Respond ONLY with a JSON array of exercise names (strings) from the
        untested catalog list, ordered by priority.  Example:
        ["squat", "leg press", "romanian deadlift"]

        Do not include exercises already tested. Do not add any commentary
        outside the JSON array.
    """).strip()


def _ask_nemotron(prompt: str) -> list[str]:
    """Call Nemotron 3 Nano and parse a JSON list of exercise names from the reply."""
    import json
    import re

    client = OpenAI(api_key=NVIDIA_API_KEY, base_url=NVIDIA_BASE_URL)

    logger.debug("Calling Nemotron 3 Nano for OOD candidate selection...")
    response = client.chat.completions.create(
        model=NEMOTRON_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=512,
    )

    raw = response.choices[0].message.content or ""
    logger.debug("Nemotron raw reply: %s", raw)

    # Extract the JSON array even if the model wraps it in markdown fences.
    match = re.search(r"\[.*?\]", raw, re.DOTALL)
    if not match:
        logger.warning("Nemotron reply contained no JSON array; no candidates.")
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

def identify_exercise(
    patient_id: str,
    query_video_path: str,
    similarity_fn: SimilarityFn,
) -> str | None:
    """Identify the exercise being performed in *query_video_path*.

    Returns the exercise name (str) on a confident match, or None if the
    search is exhausted with no candidate returning a valid reference video.
    """
    profile = get_patient_profile(patient_id)
    if profile is None:
        raise ValueError(f"Unknown patient id: {patient_id!r}")

    kaggle_catalog = list(KAGGLE_EXERCISES)
    already_tried: set[str] = set()

    # ── 1. In-domain pass ────────────────────────────────────────────────────
    logger.info(
        "[%s] In-domain pass: scoring %d prescribed exercises.",
        patient_id,
        len(profile.exercises),
    )
    in_domain_scores = _score_exercises(query_video_path, profile.exercises, similarity_fn)
    already_tried.update(profile.exercises)

    best = _best(in_domain_scores)
    if best and best.score >= THRESHOLD:
        logger.info(
            "[%s] In-domain match: %r (%.4f)", patient_id, best.exercise, best.score
        )
        return best.exercise

    logger.info(
        "[%s] No in-domain match (best=%.4f). Entering OOD reasoning loop.",
        patient_id,
        best.score if best else 0.0,
    )

    # Accumulate all scores so the model has the full picture each round.
    all_scores: list[_Score] = list(in_domain_scores)

    # ── 2. OOD reasoning loop ────────────────────────────────────────────────
    # The exercise is guaranteed to be in the Kaggle catalog, so we keep going
    # until Nemotron returns no new candidates (all untried options exhausted).
    round_num = 0
    while True:
        round_num += 1
        logger.info("[%s] OOD round %d", patient_id, round_num)

        prompt = _build_ood_prompt(
            patient_exercises=profile.exercises,
            all_scores_so_far=all_scores,
            already_tried=already_tried,
            kaggle_catalog=kaggle_catalog,
        )
        candidates = _ask_nemotron(prompt)

        # Only test exercises that are in the catalog and not yet tried.
        valid_candidates = [
            c for c in candidates if c in kaggle_catalog and c not in already_tried
        ]

        if not valid_candidates:
            # Model has no new ideas and all candidates are exhausted.
            logger.info("[%s] No new valid candidates returned. Stopping.", patient_id)
            break

        logger.info("[%s] Testing candidates: %s", patient_id, valid_candidates)
        round_scores = _score_exercises(query_video_path, valid_candidates, similarity_fn)
        already_tried.update(valid_candidates)
        all_scores.extend(round_scores)

        best = _best(round_scores)
        if best and best.score >= THRESHOLD:
            logger.info(
                "[%s] OOD match: %r (%.4f)", patient_id, best.exercise, best.score
            )
            return best.exercise

        logger.info(
            "[%s] Round %d best: %s=%.4f — continuing.",
            patient_id,
            round_num,
            best.exercise if best else "n/a",
            best.score if best else 0.0,
        )

    # All candidates exhausted without a match — should not happen in practice
    # since the exercise is guaranteed to be in the catalog and have a video.
    all_scores.sort(key=lambda s: s.score, reverse=True)
    logger.error(
        "[%s] Identification failed. Full score table:\n%s",
        patient_id,
        "\n".join(f"  {s.exercise}: {s.score:.4f}" for s in all_scores),
    )
    return None
