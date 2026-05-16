import sys
import cv2

DEFAULT_MODEL      = "yolo11l.pt"
DEFAULT_CONFIDENCE = 0.5
PERSON_CLASS       = 0


def load_model(model_name: str = DEFAULT_MODEL):
    from ultralytics import YOLO
    return YOLO(model_name)


def extract_bounding_boxes(model, frame, confidence_threshold: float):
    results = model.track(
        frame,
        persist=True,
        classes=[PERSON_CLASS],
        conf=confidence_threshold,
        iou=0.45,
        verbose=False,
    )
    return results[0].boxes if results and results[0].boxes is not None else []


def display_bounding_box_on_person(model, frame, confidence_threshold: float):
    boxes = extract_bounding_boxes(model, frame, confidence_threshold)

    for box in boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

    cv2.imshow("Person Detector", frame)


if __name__ == "__main__":
    model_name = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL
    model      = load_model(model_name)

    cap = cv2.VideoCapture(0)

    while cap.isOpened():
        ok, frame = cap.read()
        if not ok:
            break

        display_bounding_box_on_person(model, frame, DEFAULT_CONFIDENCE)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()