"""
Video Embedding & Similarity Pipeline — S3D (PyTorch)

torch and torchvision are imported lazily (inside functions) to prevent
the module-level import from initialising the MPS/CUDA runtime at import time,
which causes a mutex crash on macOS when combined with cv2's libavdevice.
"""

import numpy as np
import cv2

# ── Constants ────────────────────────────────────────────────────────────────

NUM_FRAMES = 32
FRAME_SIZE = (224, 224)


def get_device() -> str:
    """Return the best available device: CUDA → MPS → CPU."""
    import torch
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


# ── Model ────────────────────────────────────────────────────────────────────

def load_model():
    """Load pretrained S3D from torchvision, strip the classifier head."""
    import torch
    from torchvision.models.video import s3d as s3d_fn
    model = s3d_fn(pretrained=True)
    model.classifier = torch.nn.Identity()
    return model.eval().to(get_device())


# ── Frames ───────────────────────────────────────────────────────────────────

def extract_frames(video_path: str) -> np.ndarray:
    """Read video → (32, 224, 224, 3) float32 in [0, 1]."""
    cap    = cv2.VideoCapture(video_path)
    total  = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    idxs   = np.linspace(0, total - 1, NUM_FRAMES, dtype=int)
    frames = []

    for i in idxs:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(i))
        ok, frame = cap.read()
        if not ok or frame is None:
            frame = frames[-1] if frames else np.zeros((*FRAME_SIZE, 3), dtype=np.uint8)
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame = cv2.resize(frame, FRAME_SIZE)
        frames.append(frame)

    cap.release()
    return (np.stack(frames) / 255.0).astype(np.float32)


# ── Embed ────────────────────────────────────────────────────────────────────

def embed(model, video_path: str) -> np.ndarray:
    """Video path → L2-normalised (1024,) embedding."""
    import torch
    frames = extract_frames(video_path)
    tensor = torch.from_numpy(frames).permute(3, 0, 1, 2).unsqueeze(0).to(get_device())
    with torch.no_grad():
        emb = model(tensor).squeeze(0).cpu().numpy()
    return (emb / np.linalg.norm(emb)).astype(np.float32)


# ── Similarity ───────────────────────────────────────────────────────────────

def compute_similarity(references: np.ndarray, query: np.ndarray) -> np.ndarray:
    """(B, 1024) references × (1024,) query → (B,) cosine similarity scores."""
    return (references @ query).astype(np.float32)


def determine_best_match(scores: np.ndarray, labels: list, min_thresh: float = 0.75):
    """Best label above threshold, or None if OOD."""
    best = int(np.argmax(scores))
    return labels[best] if scores[best] >= min_thresh else None


if __name__ == "__main__":
    import os
    from tqdm import tqdm
    from collections import defaultdict

    model    = load_model()
    data_dir = "workout_videos"
    workout_types = [d for d in os.listdir(data_dir) if d not in ("__pycache__", ".DS_Store")]
    type_to_embd  = defaultdict(list)

    for workout_type in workout_types:
        videos = os.listdir(os.path.join(data_dir, workout_type))
        for video_file in tqdm(videos, leave=False):
            embd = embed(model, os.path.join(data_dir, workout_type, video_file))
            type_to_embd[workout_type].append(embd)

    for workout_type in workout_types:
        type_to_embd[workout_type] = np.stack(type_to_embd[workout_type])

    emb = embed(model, "workout_videos/barbell biceps curl/barbell biceps curl_3.mp4")
    similarities = {wt: float(np.mean(compute_similarity(type_to_embd[wt], emb))) for wt in workout_types}
    labels = list(similarities.keys())
    scores = np.array(list(similarities.values()))
    for label, score in zip(labels, scores):
        print(f"{label:<40} | {score:.3f}")
    print(determine_best_match(scores, labels, min_thresh=0.75))
