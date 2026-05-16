import numpy as np

import video_embeder
import pipeline


if __name__ == '__main__':
    model = video_embeder.load_model()

    # Load (or compute + cache) all reference embeddings.
    # Cached .pt files are stored under data/embeddings/ and reused on future runs.
    type_to_embd = pipeline.load_reference_embeddings(model)

    # Test classification on a sample query video
    test_video = str(pipeline.DEFAULT_REFERENCE_DIR / "barbell biceps curl" / "barbell biceps curl_3.mp4")
    emb = video_embeder.embed(model, test_video)

    similarities = {}
    for workout_type, ref_embds in type_to_embd.items():
        scores = video_embeder.compute_similarity(ref_embds, emb)
        similarities[workout_type] = float(np.mean(scores))

    labels = list(similarities.keys())
    scores = np.array(list(similarities.values()))

    for label, score in zip(labels, scores):
        print(f"{label:<40} | {round(float(score), 3):.3f}")

    label = video_embeder.determine_best_match(scores, labels, min_thresh=0.75)
    print(label)
