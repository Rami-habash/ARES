"""
Form analysis — rich kinematic comparison of a patient's movement vs a reference video.

Produces structured, descriptive data designed for an agent to reason over:
  - Per-joint deviation with direction, range-of-motion comparison, and phase breakdown
  - Left/right symmetry analysis
  - Temporal fatigue trend
  - Plain-English description per joint
  - Actionable coaching cues
  - A comprehensive agent_context block the agent can reason over directly

Pipeline (called through pipeline.py wrappers — do not import pipeline here):
  extract_reference_keypoints → compute_joint_angles → compare_sequences
  or all-in-one: compare_form(patient_landmarks, reference_video, pose_model, bbox_model)
"""

from __future__ import annotations

from typing import TypedDict

import cv2
import numpy as np

import bounding_box
import keypoint_extraction

# ── Joint Definitions ─────────────────────────────────────────────────────────
# (landmark_A, landmark_B, landmark_C) — angle measured at B.
# MediaPipe full-body indices (33 landmarks total).

JOINT_ANGLES: dict[str, tuple[int, int, int]] = {
    "left_knee":      (23, 25, 27),   # left hip    → left knee    → left ankle
    "right_knee":     (24, 26, 28),   # right hip   → right knee   → right ankle
    "left_hip":       (11, 23, 25),   # left shoulder  → left hip  → left knee
    "right_hip":      (12, 24, 26),   # right shoulder → right hip → right knee
    "left_elbow":     (11, 13, 15),   # left shoulder  → left elbow  → left wrist
    "right_elbow":    (12, 14, 16),   # right shoulder → right elbow → right wrist
    "left_shoulder":  (23, 11, 13),   # left hip  → left shoulder  → left elbow
    "right_shoulder": (24, 12, 14),   # right hip → right shoulder → right elbow
    "left_ankle":     (25, 27, 31),   # left knee  → left ankle  → left foot index
    "right_ankle":    (26, 28, 32),   # right knee → right ankle → right foot index
}

# Paired joints for bilateral symmetry analysis
JOINT_PAIRS: list[tuple[str, str, str]] = [
    ("left_knee",      "right_knee",      "knees"),
    ("left_hip",       "right_hip",       "hips"),
    ("left_elbow",     "right_elbow",     "elbows"),
    ("left_shoulder",  "right_shoulder",  "shoulders"),
    ("left_ankle",     "right_ankle",     "ankles"),
]

_VISIBILITY_MIN   = 0.3    # landmarks below this are treated as missing
_DIRECTION_MARGIN = 5.0    # degrees — within this is "on_track"

_SEVERITY_THRESHOLDS = [
    (10.0,         "good"),
    (20.0,         "minor"),
    (35.0,         "moderate"),
    (float("inf"), "major"),
]

# ── Return Types ──────────────────────────────────────────────────────────────

class PhaseStats(TypedDict):
    """Mean angle deviation in one temporal phase of the movement."""
    phase:         str    # "early" | "mid" | "late"
    mean_deg_diff: float
    worst_joint:   str | None


class JointDeviation(TypedDict):
    joint:            str
    severity:         str             # "good" | "minor" | "moderate" | "major"
    direction:        str             # "under_flexed" | "over_flexed" | "on_track" | "variable"
    mean_deg_diff:    float
    max_deg_diff:     float
    patient_range:    tuple[float, float]    # (min_angle, max_angle) patient achieves
    reference_range:  tuple[float, float]   # (min_angle, max_angle) reference achieves
    phase_breakdown:  dict[str, float]      # {"early": deg, "mid": deg, "late": deg}
    description:      str             # natural-language description for the agent


class SymmetryAnalysis(TypedDict):
    joint_pair:       str             # e.g. "knees"
    left_mean_diff:   float
    right_mean_diff:  float
    asymmetry_deg:    float           # abs(left - right deviation)
    worse_side:       str | None      # "left" | "right" | None (symmetric)
    description:      str


class FormComparison(TypedDict):
    overall_score:      float                    # 0.0 (worst) → 1.0 (perfect)
    joint_deviations:   list[JointDeviation]     # all joints, sorted worst first
    worst_joints:       list[str]                # moderate/major joints
    symmetry_analysis:  list[SymmetryAnalysis]   # per paired joint group
    phase_breakdown:    list[PhaseStats]         # early / mid / late summary
    fatigue_indicator:  str | None               # "degrading" | "stable" | "improving"
    frame_scores:       list[float | None]       # mean deg error per DTW-aligned frame
    coaching_cues:      list[str]                # actionable bullet points for the agent
    agent_context:      str                      # full structured narrative for LLM reasoning
    summary:            str                      # one-paragraph session summary


# ── Helpers ───────────────────────────────────────────────────────────────────

def _angle_deg(a: dict, b: dict, c: dict) -> float:
    """Angle at vertex b in the triangle a-b-c, in degrees."""
    ba = np.array([a["x"] - b["x"], a["y"] - b["y"], a["z"] - b["z"]])
    bc = np.array([c["x"] - b["x"], c["y"] - b["y"], c["z"] - b["z"]])
    denom = np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-8
    return float(np.degrees(np.arccos(np.clip(np.dot(ba, bc) / denom, -1.0, 1.0))))


def _severity(mean_deg: float) -> str:
    for threshold, label in _SEVERITY_THRESHOLDS:
        if mean_deg < threshold:
            return label
    return "major"


def _direction(patient_mean: float, ref_mean: float) -> str:
    """
    Determine the direction of deviation.
    Smaller angle = more flexion. Larger angle = more extension.
    under_flexed: patient doesn't bend enough (angle too large vs reference)
    over_flexed:  patient bends too much (angle too small vs reference)
    """
    diff = patient_mean - ref_mean
    if abs(diff) <= _DIRECTION_MARGIN:
        return "on_track"
    return "under_flexed" if diff > 0 else "over_flexed"


def _landmarks_from_crop(pose_model, crop: np.ndarray, timestamp_ms: int) -> list[dict]:
    lm_list = keypoint_extraction.extract_keypoints(pose_model, crop, timestamp_ms)
    if not lm_list:
        return []
    return [
        {"x": lm.x, "y": lm.y, "z": lm.z, "visibility": getattr(lm, "visibility", 1.0)}
        for lm in lm_list[0]
    ]


def _nanmean(values: list[float]) -> float | None:
    clean = [v for v in values if not np.isnan(v)]
    return float(np.mean(clean)) if clean else None


def _range(values: list[float]) -> tuple[float, float] | None:
    clean = [v for v in values if not np.isnan(v)]
    return (float(np.min(clean)), float(np.max(clean))) if clean else None


# ── Keypoint Extraction ───────────────────────────────────────────────────────

def extract_reference_keypoints(
    pose_model,
    video_path: str,
    bbox_model=None,
    num_frames: int = 64,
) -> list[list[dict]]:
    """
    Extract MediaPipe landmark sequences from a reference video.

    Crops to the largest detected person if bbox_model is provided (recommended
    for wide-angle footage). For clean single-person clips, bbox_model can be None.
    """
    cap   = cv2.VideoCapture(video_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps   = cap.get(cv2.CAP_PROP_FPS) or 30.0

    sample_idxs = np.linspace(0, total - 1, min(num_frames, total), dtype=int)
    all_landmarks: list[list[dict]] = []

    for idx in sample_idxs:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ok, frame = cap.read()
        if not ok:
            all_landmarks.append([])
            continue

        h, w = frame.shape[:2]
        crop = frame

        if bbox_model is not None:
            boxes = bounding_box.extract_bounding_boxes(bbox_model, frame, 0.3)
            if boxes:
                largest = max(
                    boxes,
                    key=lambda b: (int(b.xyxy[0][2]) - int(b.xyxy[0][0]))
                                * (int(b.xyxy[0][3]) - int(b.xyxy[0][1]))
                )
                x1, y1, x2, y2 = map(int, largest.xyxy[0])
                crop = frame[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]

        timestamp_ms = int(idx * (1000.0 / fps))
        all_landmarks.append(
            _landmarks_from_crop(pose_model, crop, timestamp_ms) if crop.size > 0 else []
        )

    cap.release()
    return all_landmarks


# ── Angle Computation ─────────────────────────────────────────────────────────

def compute_joint_angles(
    landmarks_sequence: list[list[dict]],
) -> dict[str, list[float]]:
    """
    Convert a per-frame landmark sequence into named joint angle sequences.
    Returns {joint_name: [angle_deg, ...]} with float("nan") for low-visibility frames.
    """
    angles: dict[str, list[float]] = {joint: [] for joint in JOINT_ANGLES}

    for frame_lms in landmarks_sequence:
        for joint, (i, j, k) in JOINT_ANGLES.items():
            if frame_lms and len(frame_lms) > max(i, j, k):
                a, b, c = frame_lms[i], frame_lms[j], frame_lms[k]
                min_vis = min(
                    a.get("visibility", 1.0),
                    b.get("visibility", 1.0),
                    c.get("visibility", 1.0),
                )
                angles[joint].append(
                    _angle_deg(a, b, c) if min_vis >= _VISIBILITY_MIN else float("nan")
                )
            else:
                angles[joint].append(float("nan"))

    return angles


# ── DTW Alignment ─────────────────────────────────────────────────────────────

def _dtw_path(
    pat_vecs: np.ndarray,   # (N, J)
    ref_vecs: np.ndarray,   # (M, J)
) -> list[tuple[int, int]]:
    """DTW alignment path between two angle-vector sequences. NaN-safe."""
    n, m = len(pat_vecs), len(ref_vecs)
    cost = np.full((n, m), np.inf)

    def dist(i: int, j: int) -> float:
        a, b  = pat_vecs[i], ref_vecs[j]
        valid = ~(np.isnan(a) | np.isnan(b))
        return float(np.mean(np.abs(a[valid] - b[valid]))) if valid.any() else 0.0

    cost[0, 0] = dist(0, 0)
    for i in range(1, n):
        cost[i, 0] = cost[i - 1, 0] + dist(i, 0)
    for j in range(1, m):
        cost[0, j] = cost[0, j - 1] + dist(0, j)
    for i in range(1, n):
        for j in range(1, m):
            cost[i, j] = dist(i, j) + min(cost[i - 1, j], cost[i, j - 1], cost[i - 1, j - 1])

    i, j = n - 1, m - 1
    path = [(i, j)]
    while i > 0 or j > 0:
        if i == 0:
            j -= 1
        elif j == 0:
            i -= 1
        else:
            step = int(np.argmin([cost[i - 1, j], cost[i, j - 1], cost[i - 1, j - 1]]))
            if step == 0:   i -= 1
            elif step == 1: j -= 1
            else:           i -= 1; j -= 1
        path.append((i, j))

    path.reverse()
    return path


# ── Rich Comparison ───────────────────────────────────────────────────────────

def _phase_breakdown(
    path: list[tuple[int, int]],
    pat_mat: np.ndarray,
    ref_mat: np.ndarray,
    joints: list[str],
) -> list[PhaseStats]:
    """Split the DTW path into early/mid/late thirds and compute mean error per phase."""
    n = len(path)
    thirds = [
        ("early", path[:n // 3]),
        ("mid",   path[n // 3: 2 * n // 3]),
        ("late",  path[2 * n // 3:]),
    ]
    result: list[PhaseStats] = []
    for phase_name, segment in thirds:
        if not segment:
            continue
        joint_errors: dict[str, list[float]] = {j: [] for j in joints}
        for pi, ri in segment:
            for ji, j in enumerate(joints):
                pv, rv = pat_mat[pi, ji], ref_mat[ri, ji]
                if not (np.isnan(pv) or np.isnan(rv)):
                    joint_errors[j].append(abs(float(pv) - float(rv)))
        joint_means = {j: float(np.mean(v)) for j, v in joint_errors.items() if v}
        worst = max(joint_means, key=joint_means.get) if joint_means else None
        phase_mean = float(np.mean(list(joint_means.values()))) if joint_means else 0.0
        result.append(PhaseStats(phase=phase_name, mean_deg_diff=round(phase_mean, 1), worst_joint=worst))
    return result


def _symmetry_analysis(
    joint_means: dict[str, float],
) -> list[SymmetryAnalysis]:
    """Compare left vs right deviation for each paired joint group."""
    results: list[SymmetryAnalysis] = []
    for left_joint, right_joint, pair_name in JOINT_PAIRS:
        left_dev  = joint_means.get(left_joint)
        right_dev = joint_means.get(right_joint)
        if left_dev is None or right_dev is None:
            continue
        asym   = abs(left_dev - right_dev)
        worse  = "left" if left_dev > right_dev else ("right" if right_dev > left_dev else None)
        if asym < 5.0:
            desc = f"{pair_name.capitalize()} are symmetrical (left {left_dev:.0f}° vs right {right_dev:.0f}° deviation)."
        else:
            desc = (
                f"{pair_name.capitalize()} show {asym:.0f}° asymmetry — "
                f"{worse} side is worse ({left_dev if worse == 'left' else right_dev:.0f}° vs "
                f"{right_dev if worse == 'left' else left_dev:.0f}°). "
                "Consider unilateral corrective exercises."
            )
        results.append(SymmetryAnalysis(
            joint_pair=pair_name,
            left_mean_diff=round(left_dev, 1),
            right_mean_diff=round(right_dev, 1),
            asymmetry_deg=round(asym, 1),
            worse_side=worse,
            description=desc,
        ))
    return results


def _fatigue_indicator(frame_scores: list[float | None]) -> str | None:
    """Compare mean error in first vs last third to detect form degradation."""
    clean = [(i, s) for i, s in enumerate(frame_scores) if s is not None]
    if len(clean) < 6:
        return None
    n = len(clean)
    early_mean = float(np.mean([s for _, s in clean[:n // 3]]))
    late_mean  = float(np.mean([s for _, s in clean[2 * n // 3:]]))
    diff = late_mean - early_mean
    if diff > 5.0:
        return "degrading"
    if diff < -5.0:
        return "improving"
    return "stable"


def _joint_description(
    joint: str,
    direction: str,
    severity: str,
    mean_diff: float,
    max_diff: float,
    patient_range: tuple[float, float],
    ref_range: tuple[float, float],
    worst_phase: str | None,
    phase_breakdown: dict[str, float],
) -> str:
    """Generate a natural-language description of a single joint's deviation."""
    readable     = joint.replace("_", " ")
    pat_lo, pat_hi = patient_range
    ref_lo, ref_hi = ref_range
    phase_note   = f", worst during the {worst_phase} phase" if worst_phase else ""
    phase_trend  = ""

    if len(phase_breakdown) == 3:
        vals = list(phase_breakdown.values())
        if vals[-1] - vals[0] > 8:
            phase_trend = " Form degrades as the movement progresses."
        elif vals[0] - vals[-1] > 8:
            phase_trend = " Form improves through the movement."

    if direction == "under_flexed":
        action = (
            f"not bending enough — patient reaches {pat_lo:.0f}°–{pat_hi:.0f}° "
            f"vs reference {ref_lo:.0f}°–{ref_hi:.0f}° (insufficient range of motion)"
        )
    elif direction == "over_flexed":
        action = (
            f"bending more than the reference — patient reaches {pat_lo:.0f}°–{pat_hi:.0f}° "
            f"vs reference {ref_lo:.0f}°–{ref_hi:.0f}° (excessive flexion)"
        )
    else:
        action = (
            f"tracking reference range ({pat_lo:.0f}°–{pat_hi:.0f}° vs "
            f"reference {ref_lo:.0f}°–{ref_hi:.0f}°)"
        )

    return (
        f"{readable.capitalize()} [{severity.upper()}]: {action}. "
        f"Average deviation {mean_diff:.0f}° (max {max_diff:.0f}°){phase_note}.{phase_trend}"
    )


def _coaching_cues(
    deviations: list[JointDeviation],
    symmetry: list[SymmetryAnalysis],
    fatigue: str | None,
) -> list[str]:
    """Generate actionable, specific coaching instructions for the agent to relay."""
    cues: list[str] = []

    for dev in deviations:
        if dev["severity"] in ("good", "minor"):
            continue
        j       = dev["joint"].replace("_", " ")
        pat_lo  = dev["patient_range"][0]
        ref_lo  = dev["reference_range"][0]
        pat_hi  = dev["patient_range"][1]
        ref_hi  = dev["reference_range"][1]
        worst_p = max(dev["phase_breakdown"], key=dev["phase_breakdown"].get) if dev["phase_breakdown"] else None

        if dev["direction"] == "under_flexed":
            cues.append(
                f"Increase {j} range of motion: you're reaching {pat_lo:.0f}° "
                f"but should reach {ref_lo:.0f}°. "
                + (f"Focus especially on the {worst_p} phase." if worst_p else "")
            )
        elif dev["direction"] == "over_flexed":
            cues.append(
                f"Reduce {j} flexion: you're going to {pat_lo:.0f}° "
                f"but the target is {ref_lo:.0f}°. "
                + (f"This is most pronounced in the {worst_p} phase." if worst_p else "")
            )
        else:
            cues.append(
                f"Work on {j} consistency — deviation averages {dev['mean_deg_diff']:.0f}° "
                f"from reference."
            )

    for sym in symmetry:
        if sym["asymmetry_deg"] >= 10.0 and sym["worse_side"]:
            cues.append(
                f"Address {sym['joint_pair']} asymmetry — your {sym['worse_side']} side "
                f"is {sym['asymmetry_deg']:.0f}° worse than your other side. "
                "Try single-leg or unilateral variations to correct the imbalance."
            )

    if fatigue == "degrading":
        cues.append(
            "Form degrades toward the end of the movement. "
            "Consider reducing repetitions, increasing rest time, or lowering resistance "
            "until baseline form is consistent throughout."
        )
    elif fatigue == "improving":
        cues.append(
            "Form improves as the movement progresses — you may be warming up slowly. "
            "Add a longer warm-up set before working sets."
        )

    return cues


def _build_agent_context(
    deviations: list[JointDeviation],
    symmetry: list[SymmetryAnalysis],
    phase_breakdown: list[PhaseStats],
    fatigue: str | None,
    overall_score: float,
) -> str:
    """
    Build a structured narrative the agent can reason over directly.
    This is the primary input for LLM-based coaching generation.
    """
    lines: list[str] = []

    lines.append("=== FORM ANALYSIS REPORT ===\n")
    lines.append(f"Overall form score: {overall_score:.0%}\n")

    # Reference profile
    lines.append("REFERENCE MOVEMENT PROFILE:")
    for dev in deviations:
        ref_lo, ref_hi = dev["reference_range"]
        lines.append(f"  • {dev['joint'].replace('_', ' ')}: {ref_lo:.0f}°–{ref_hi:.0f}° range of motion")
    lines.append("")

    # Patient profile
    lines.append("PATIENT MOVEMENT PROFILE:")
    for dev in deviations:
        pat_lo, pat_hi = dev["patient_range"]
        flag = f" [{dev['severity'].upper()}]" if dev["severity"] != "good" else ""
        lines.append(
            f"  • {dev['joint'].replace('_', ' ')}: {pat_lo:.0f}°–{pat_hi:.0f}° range of motion{flag}"
        )
    lines.append("")

    # Joint deviations
    lines.append("JOINT DEVIATIONS (worst first):")
    for dev in deviations:
        if dev["severity"] == "good":
            continue
        lines.append(f"  • {dev['description']}")
        pb = dev["phase_breakdown"]
        if pb:
            phase_str = "  |  ".join(f"{p}: {v:.0f}°" for p, v in pb.items())
            lines.append(f"      Phase breakdown: {phase_str}")
    lines.append("")

    # Symmetry
    lines.append("BILATERAL SYMMETRY:")
    for sym in symmetry:
        lines.append(f"  • {sym['description']}")
    lines.append("")

    # Temporal trend
    lines.append("TEMPORAL PATTERN (early → mid → late):")
    for ps in phase_breakdown:
        wj = f" (worst: {ps['worst_joint'].replace('_', ' ')})" if ps["worst_joint"] else ""
        lines.append(f"  • {ps['phase'].capitalize()} phase: {ps['mean_deg_diff']:.0f}° avg error{wj}")
    fatigue_str = {
        "degrading":  "Form degrades significantly by the end — fatigue or technique breakdown.",
        "improving":  "Form improves through the movement — likely warming up slowly.",
        "stable":     "Form is consistent throughout the movement.",
        None:         "Insufficient data for temporal trend analysis.",
    }[fatigue]
    lines.append(f"  → {fatigue_str}")
    lines.append("")

    lines.append("=== END REPORT ===")
    return "\n".join(lines)


def _session_summary(
    deviations: list[JointDeviation],
    symmetry: list[SymmetryAnalysis],
    fatigue: str | None,
    overall_score: float,
) -> str:
    """One-paragraph plain-English summary for end-of-session display."""
    score_pct = f"{overall_score:.0%}"
    flagged   = [d for d in deviations if d["severity"] in ("major", "moderate")]
    good_joints = [d["joint"].replace("_", " ") for d in deviations if d["severity"] == "good"]

    if not flagged:
        return (
            f"Excellent session — overall form score {score_pct}. "
            "No significant joint deviations detected. "
            + (f"Strongest areas: {', '.join(good_joints[:3])}." if good_joints else "")
        )

    issues = [d["joint"].replace("_", " ") for d in flagged[:3]]
    asym_note = ""
    worst_asym = max(symmetry, key=lambda s: s["asymmetry_deg"], default=None)
    if worst_asym and worst_asym["asymmetry_deg"] >= 10.0:
        asym_note = (
            f" Notable left-right asymmetry in the {worst_asym['joint_pair']} "
            f"({worst_asym['asymmetry_deg']:.0f}° difference)."
        )

    fatigue_note = {
        "degrading": " Form broke down toward the end — consider reducing volume.",
        "improving": " Form improved through the session — try a longer warm-up.",
        "stable":    "",
        None:        "",
    }[fatigue]

    return (
        f"Overall form score: {score_pct}. "
        f"Primary areas to address: {', '.join(issues)}. "
        f"{asym_note}{fatigue_note} "
        "Review the coaching cues and joint deviation breakdown for specific corrections."
    ).strip()


# ── Top-level Functions ───────────────────────────────────────────────────────

def compare_sequences(
    patient_angles: dict[str, list[float]],
    reference_angles: dict[str, list[float]],
) -> FormComparison:
    """
    DTW-align two joint-angle sequences and produce a rich FormComparison.
    Both inputs should come from compute_joint_angles().
    """
    joints  = list(JOINT_ANGLES.keys())

    def to_matrix(angle_dict: dict[str, list[float]]) -> np.ndarray:
        n = len(next(iter(angle_dict.values())))
        return np.array([[angle_dict[j][i] for j in joints] for i in range(n)], dtype=float)

    pat_mat = to_matrix(patient_angles)    # (N, J)
    ref_mat = to_matrix(reference_angles)  # (M, J)

    path = _dtw_path(pat_mat, ref_mat)

    # Collect per-joint diffs along the DTW path
    joint_diffs:    dict[str, list[float]] = {j: [] for j in joints}
    frame_scores:   list[float | None]     = []

    for pi, ri in path:
        pf, rf  = pat_mat[pi], ref_mat[ri]
        valid   = ~(np.isnan(pf) | np.isnan(rf))
        if valid.any():
            abs_diffs = np.abs(pf - rf)
            frame_scores.append(round(float(np.mean(abs_diffs[valid])), 2))
            for ji, j in enumerate(joints):
                if not (np.isnan(pf[ji]) or np.isnan(rf[ji])):
                    joint_diffs[j].append(abs(float(pf[ji]) - float(rf[ji])))
        else:
            frame_scores.append(None)

    # Phase breakdown (early / mid / late)
    phases = _phase_breakdown(path, pat_mat, ref_mat, joints)
    phase_dict_per_joint: dict[str, dict[str, float]] = {j: {} for j in joints}
    # Recompute per-joint phase breakdown for the JointDeviation.phase_breakdown field
    n_path = len(path)
    for phase_name, segment in [
        ("early", path[:n_path // 3]),
        ("mid",   path[n_path // 3: 2 * n_path // 3]),
        ("late",  path[2 * n_path // 3:]),
    ]:
        for ji, j in enumerate(joints):
            vals = []
            for pi, ri in segment:
                pv, rv = pat_mat[pi, ji], ref_mat[ri, ji]
                if not (np.isnan(pv) or np.isnan(rv)):
                    vals.append(abs(float(pv) - float(rv)))
            phase_dict_per_joint[j][phase_name] = round(float(np.mean(vals)), 1) if vals else 0.0

    # Build JointDeviation entries
    deviations: list[JointDeviation] = []
    joint_means: dict[str, float] = {}
    for ji, j in enumerate(joints):
        diffs = joint_diffs[j]
        if not diffs:
            continue
        mean_diff = float(np.mean(diffs))
        max_diff  = float(np.max(diffs))
        joint_means[j] = mean_diff

        pat_vals = [patient_angles[j][i] for i in range(len(patient_angles[j])) if not np.isnan(patient_angles[j][i])]
        ref_vals = [reference_angles[j][i] for i in range(len(reference_angles[j])) if not np.isnan(reference_angles[j][i])]
        pat_rng  = (round(min(pat_vals), 1), round(max(pat_vals), 1)) if pat_vals else (0.0, 0.0)
        ref_rng  = (round(min(ref_vals), 1), round(max(ref_vals), 1)) if ref_vals else (0.0, 0.0)

        pat_mean = float(np.mean(pat_vals)) if pat_vals else 0.0
        ref_mean = float(np.mean(ref_vals)) if ref_vals else 0.0
        dir_     = _direction(pat_mean, ref_mean)
        sev      = _severity(mean_diff)
        pb       = phase_dict_per_joint[j]
        worst_ph = max(pb, key=pb.get) if pb else None

        deviations.append(JointDeviation(
            joint=j,
            severity=sev,
            direction=dir_,
            mean_deg_diff=round(mean_diff, 1),
            max_deg_diff=round(max_diff, 1),
            patient_range=pat_rng,
            reference_range=ref_rng,
            phase_breakdown=pb,
            description=_joint_description(j, dir_, sev, mean_diff, max_diff, pat_rng, ref_rng, worst_ph, pb),
        ))

    deviations.sort(key=lambda d: -d["mean_deg_diff"])
    worst_joints = [d["joint"] for d in deviations if d["severity"] in ("major", "moderate")][:5]

    symmetry = _symmetry_analysis(joint_means)
    fatigue  = _fatigue_indicator(frame_scores)

    valid_scores = [s for s in frame_scores if s is not None]
    overall = float(np.clip(1.0 - np.mean(valid_scores) / 90.0, 0.0, 1.0)) if valid_scores else 0.0
    overall = round(overall, 3)

    cues         = _coaching_cues(deviations, symmetry, fatigue)
    agent_ctx    = _build_agent_context(deviations, symmetry, phases, fatigue, overall)
    summary      = _session_summary(deviations, symmetry, fatigue, overall)

    return FormComparison(
        overall_score=overall,
        joint_deviations=deviations,
        worst_joints=worst_joints,
        symmetry_analysis=symmetry,
        phase_breakdown=phases,
        fatigue_indicator=fatigue,
        frame_scores=frame_scores,
        coaching_cues=cues,
        agent_context=agent_ctx,
        summary=summary,
    )


def compare_form(
    patient_landmarks: list[list[dict]],
    reference_video: str,
    pose_model,
    bbox_model=None,
    num_frames: int = 64,
) -> FormComparison:
    """
    End-to-end form comparison given pre-extracted patient landmarks.
    Call through pipeline.compare_form — that handles model loading.
    """
    ref_landmarks = extract_reference_keypoints(pose_model, reference_video, bbox_model, num_frames)
    ref_angles    = compute_joint_angles(ref_landmarks)
    pat_angles    = compute_joint_angles(patient_landmarks)
    return compare_sequences(pat_angles, ref_angles)
