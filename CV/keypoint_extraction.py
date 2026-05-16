import os
import cv2

MODEL_PATH         = "pose_landmarker_full.task"
DEFAULT_CONFIDENCE = 0.5

BODY_INDICES = {0, 11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28}

CONNECTIONS = [
    (11, 12), (11, 13), (13, 15), (12, 14), (14, 16),  # arms
    (11, 23), (12, 24), (23, 24),                        # torso
    (23, 25), (25, 27), (24, 26), (26, 28),              # legs
    (0, 11),  (0, 12),                                   # nose→shoulders
]


def load_model(confidence: float = DEFAULT_CONFIDENCE):
    import mediapipe as mp_module
    from mediapipe.tasks import python as mp_tasks
    from mediapipe.tasks.python.vision import PoseLandmarker, PoseLandmarkerOptions, RunningMode

    if not os.path.exists(MODEL_PATH):
        import urllib.request
        url = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task"
        urllib.request.urlretrieve(url, MODEL_PATH)

    options = PoseLandmarkerOptions(
        base_options=mp_tasks.BaseOptions(model_asset_path=MODEL_PATH),
        running_mode=RunningMode.IMAGE,
        num_poses=1,
        min_pose_detection_confidence=confidence,
        min_pose_presence_confidence=confidence,
        min_tracking_confidence=confidence,
    )
    return PoseLandmarker.create_from_options(options)


def extract_keypoints(model, frame, timestamp_ms: int = 0):
    import mediapipe as mp
    rgb    = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    result = model.detect(mp_img)
    return result.pose_landmarks


def display_keypoints_on_person(model, frame, timestamp_ms: int):
    all_landmarks = extract_keypoints(model, frame, timestamp_ms)
    h, w = frame.shape[:2]

    for landmarks in (all_landmarks or []):
        for i, j in CONNECTIONS:
            if i >= len(landmarks) or j >= len(landmarks):
                continue
            a = (int(landmarks[i].x * w), int(landmarks[i].y * h))
            b = (int(landmarks[j].x * w), int(landmarks[j].y * h))
            cv2.line(frame, a, b, (200, 200, 200), 2, cv2.LINE_AA)

        for idx, lm in enumerate(landmarks):
            if idx not in BODY_INDICES:
                continue
            px, py = int(lm.x * w), int(lm.y * h)
            cv2.circle(frame, (px, py), 4, (0, 255, 0), -1, cv2.LINE_AA)


    cv2.imshow("MediaPipe Pose", frame)


if __name__ == "__main__":
    model = load_model()
    cap   = cv2.VideoCapture(0)
    fps   = cap.get(cv2.CAP_PROP_FPS) or 30.0
    idx   = 0

    while cap.isOpened():
        ok, frame = cap.read()
        if not ok:
            break

        display_keypoints_on_person(model, frame, int(idx * (1000.0 / fps)))
        idx += 1

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()
    model.close()