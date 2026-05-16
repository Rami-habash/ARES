"""
Precompute and cache S3D embeddings for all reference videos in data/videos/.

Run this once after downloading the Kaggle dataset (or whenever new videos are
added) so that identify_exercise has zero embedding latency at runtime.

Usage
-----
  cd NemoDemo && python3 precompute_embeddings.py
"""

import sys
import time
from pathlib import Path

_NEMO = Path(__file__).resolve().parent
_CV   = _NEMO.parent / "CV"
sys.path.insert(0, str(_CV))
sys.path.insert(0, str(_NEMO))

from exercise_identifier import VIDEO_ROOT, _embed, _s3d  # noqa: E402

VIDEO_EXTS = {".mp4", ".mov"}


def main():
    videos = sorted(
        vf
        for ex_dir in sorted(VIDEO_ROOT.iterdir()) if ex_dir.is_dir()
        for vf in sorted(ex_dir.iterdir()) if vf.suffix.lower() in VIDEO_EXTS
    )

    if not videos:
        print(f"No videos found under {VIDEO_ROOT}")
        return

    print(f"Loading S3D model...")
    t0 = time.time()
    _s3d()
    print(f"  ready in {time.time()-t0:.1f}s\n")

    print(f"Embedding {len(videos)} videos across {len(list(VIDEO_ROOT.iterdir()))} exercises...\n")

    total_t0 = time.time()
    cached = skipped = 0

    for i, vf in enumerate(videos, 1):
        from exercise_identifier import _cache_path
        cache = _cache_path(vf)
        ex = vf.parent.name
        if cache.exists():
            print(f"  [{i:3d}/{len(videos)}] {ex}/{vf.name}  (cached)")
            skipped += 1
            continue

        t0 = time.time()
        _embed(vf)
        elapsed = time.time() - t0
        print(f"  [{i:3d}/{len(videos)}] {ex}/{vf.name}  {elapsed:.1f}s")
        cached += 1

    total = time.time() - total_t0
    print(f"\nDone. {cached} embedded, {skipped} already cached. Total: {total:.0f}s")


if __name__ == "__main__":
    main()
