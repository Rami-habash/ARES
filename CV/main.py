import sys
import os
import cv2
import bounding_box
import keypoint_extraction


def get_output_path(input_path: str) -> str:
    base, ext = os.path.splitext(input_path)
    return f"{base}_extracted{ext}"


def process_frame(bbox_model, pose_model, frame, timestamp_ms: int, confidence: float):
    boxes = bounding_box.extract_bounding_boxes(bbox_model, frame, confidence)
    h, w  = frame.shape[:2]

    for box in boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)

        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            continue

        all_landmarks = keypoint_extraction.extract_keypoints(pose_model, crop, timestamp_ms)
        for landmarks in (all_landmarks or []):
            for i, j in keypoint_extraction.CONNECTIONS:
                if i >= len(landmarks) or j >= len(landmarks):
                    continue
                ax = int(landmarks[i].x * (x2 - x1)) + x1
                ay = int(landmarks[i].y * (y2 - y1)) + y1
                bx = int(landmarks[j].x * (x2 - x1)) + x1
                by = int(landmarks[j].y * (y2 - y1)) + y1
                cv2.line(frame, (ax, ay), (bx, by), (200, 200, 200), 2, cv2.LINE_AA)

            for idx, lm in enumerate(landmarks):
                if idx not in keypoint_extraction.BODY_INDICES:
                    continue
                px = int(lm.x * (x2 - x1)) + x1
                py = int(lm.y * (y2 - y1)) + y1
                cv2.circle(frame, (px, py), 4, (0, 255, 0), -1, cv2.LINE_AA)

    return frame


if __name__ == "__main__":
    input_path  = sys.argv[1]
    output_path = get_output_path(input_path)

    bbox_model = bounding_box.load_model()
    pose_model = keypoint_extraction.load_model()

    cap = cv2.VideoCapture(input_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    w   = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h   = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    writer = cv2.VideoWriter(output_path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))

    idx = 0
    while cap.isOpened():
        ok, frame = cap.read()
        if not ok:
            break

        frame = process_frame(bbox_model, pose_model, frame, int(idx * (1000.0 / fps)), bounding_box.DEFAULT_CONFIDENCE)
        writer.write(frame)
        idx += 1

        print(f"\rFrame {idx}", end="", flush=True)

    print(f"\nSaved to {output_path}")

    cap.release()
    writer.release()
    pose_model.close()