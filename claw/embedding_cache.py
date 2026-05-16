"""In-memory LFU embedding cache with disk-backed persistence.

Architecture
------------
RAM LFU cache (EmbeddingCache)
    └── disk cache (.pt files under data/embeddings/)
            └── S3D model (embed on cache miss)

On check-in call prefetch_for_patient(patient_id) to eagerly load the
patient's prescribed exercise embeddings into RAM before the first tick
arrives, so identification is fast from the first rep.

Eviction
--------
Least-Frequently-Used (LFU) with a configurable capacity measured in
number of (exercise, video) embedding entries. LFU is the right policy
here: prescribed exercises are hit many times per session and stay hot;
OOD catalog exercises are scored once and then rarely revisited.

Tie-breaking among entries with equal frequency uses insertion order
(FIFO within the same frequency bucket), which keeps the implementation
O(1) per operation without a secondary timestamp index.
"""

from __future__ import annotations

import logging
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

import numpy as np
import torch

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LFU core
# ---------------------------------------------------------------------------

class _LFUCache:
    """O(1) LFU cache mapping str keys to numpy arrays.

    Uses the standard doubly-linked list + frequency-bucket approach so
    get/put are both O(1).  We implement it with plain dicts + ordered
    insertion (Python 3.7+ dict order) instead of explicit linked lists
    to keep the code readable.
    """

    def __init__(self, capacity: int) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be > 0")
        self.capacity = capacity
        self._vals: dict[str, np.ndarray] = {}          # key → value
        self._freq: dict[str, int] = {}                 # key → frequency
        self._buckets: dict[int, dict[str, None]] = defaultdict(dict)  # freq → ordered key set
        self._min_freq: int = 0

    def __len__(self) -> int:
        return len(self._vals)

    def get(self, key: str) -> Optional[np.ndarray]:
        if key not in self._vals:
            return None
        self._increment(key)
        return self._vals[key]

    def put(self, key: str, value: np.ndarray) -> None:
        if key in self._vals:
            self._vals[key] = value
            self._increment(key)
            return

        if len(self._vals) >= self.capacity:
            self._evict()

        self._vals[key] = value
        self._freq[key] = 1
        self._buckets[1][key] = None
        self._min_freq = 1

    def _increment(self, key: str) -> None:
        f = self._freq[key]
        del self._buckets[f][key]
        if not self._buckets[f] and f == self._min_freq:
            self._min_freq = f + 1
        self._freq[key] = f + 1
        self._buckets[f + 1][key] = None

    def _evict(self) -> None:
        bucket = self._buckets[self._min_freq]
        victim = next(iter(bucket))   # oldest insertion in lowest-freq bucket
        del bucket[victim]
        del self._vals[victim]
        del self._freq[victim]
        logger.debug("LFU evicted: %s (freq=%d)", victim, self._min_freq)


# ---------------------------------------------------------------------------
# Public cache singleton
# ---------------------------------------------------------------------------

# Maximum number of (exercise, video-file) embedding entries held in RAM.
# 512-d float32 = 2 KB per entry; 200 entries ≈ 400 KB.
MAX_ENTRIES = 200

_cache = _LFUCache(MAX_ENTRIES)


def _ram_key(video_path: Path) -> str:
    return str(video_path.resolve())


# ---------------------------------------------------------------------------
# Disk cache helpers (re-exported here so exercise_identifier can import
# from a single place)
# ---------------------------------------------------------------------------

_VIDEO_ROOT     = Path(__file__).resolve().parent / "data" / "videos"
_EMBED_ROOT     = Path(__file__).resolve().parent / "data" / "embeddings"


def disk_cache_path(video_path: Path) -> Path:
    try:
        rel = video_path.relative_to(_VIDEO_ROOT)
    except ValueError:
        rel = Path(video_path.name)
    return _EMBED_ROOT / rel.parent / (rel.stem + ".pt")


def load_from_disk(video_path: Path) -> Optional[np.ndarray]:
    p = disk_cache_path(video_path)
    if p.exists():
        return torch.load(p, weights_only=True).numpy()
    return None


def save_to_disk(video_path: Path, emb: np.ndarray) -> None:
    p = disk_cache_path(video_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    torch.save(torch.from_numpy(emb), p)


# ---------------------------------------------------------------------------
# Main entry point used by exercise_identifier
# ---------------------------------------------------------------------------

def get_embedding(video_path: Path, s3d_model) -> np.ndarray:
    """Return the S3D embedding for video_path, using RAM → disk → model."""
    key = _ram_key(video_path)

    # 1. RAM hit
    emb = _cache.get(key)
    if emb is not None:
        return emb

    # 2. Disk hit
    emb = load_from_disk(video_path)
    if emb is not None:
        _cache.put(key, emb)
        return emb

    # 3. Compute
    _CV_DIR = Path(__file__).resolve().parent.parent / "CV"
    if str(_CV_DIR) not in sys.path:
        sys.path.insert(0, str(_CV_DIR))
    import video_embeder  # noqa: E402

    logger.debug("Computing S3D embedding for %s", video_path.name)
    emb = video_embeder.embed(s3d_model, str(video_path))
    save_to_disk(video_path, emb)
    _cache.put(key, emb)
    return emb


# ---------------------------------------------------------------------------
# Prefetch — call this on patient check-in
# ---------------------------------------------------------------------------

def prefetch_for_patient(patient_id: str, s3d_model) -> None:
    """Eagerly load RAM embeddings for a patient's prescribed exercises.

    Reads the patient profile to find prescribed exercises, then walks
    their reference video folders and warms the LFU cache.  Designed to
    be called once when the patient checks in so the first identify_exercise
    call hits RAM instead of disk.
    """
    # Import here to avoid circular deps; profile module has no CV deps.
    from patient_profile.profile import get_patient_profile

    profile = get_patient_profile(patient_id)
    if profile is None:
        logger.warning("prefetch_for_patient: unknown patient %s", patient_id)
        return

    logger.info(
        "[%s] Prefetching reference embeddings for: %s",
        patient_id, profile.exercises,
    )

    loaded = 0
    for exercise in profile.exercises:
        folder = _VIDEO_ROOT / exercise
        if not folder.is_dir():
            continue
        mp4s = sorted(f for f in folder.iterdir() if f.suffix.lower() == ".mp4")
        for vf in mp4s[:5]:   # match REFS_PER_EXERCISE = 5
            key = _ram_key(vf)
            if _cache.get(key) is not None:
                continue  # already warm
            emb = load_from_disk(vf)
            if emb is None:
                emb = get_embedding(vf, s3d_model)
            _cache.put(key, emb)
            loaded += 1

    logger.info("[%s] Prefetch complete: %d embeddings loaded into RAM cache.", patient_id, loaded)
