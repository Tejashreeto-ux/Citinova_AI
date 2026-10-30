
import cv2
import requests
import time
from pathlib import Path
from collections import Counter
from ultralytics import YOLO

print("======================================")
print("          CITINOVA AI")
print("     MULTIPLE VIDEO DETECTION")
print("======================================")

# Flask backend API
API_URL = "http://127.0.0.1:5000/api/update-traffic"

# Find the traffic_videos folder automatically
PROJECT_DIR = Path(__file__).resolve().parent.parent
VIDEO_FOLDER = PROJECT_DIR / "traffic_videos"

# Vehicle classes in the YOLO COCO model
VEHICLE_CLASSES = {
    2: "Car",
    3: "Motorcycle",
    5: "Bus",
    7: "Truck"
}

# Load YOLO model
print("Loading YOLO model...")
model = YOLO("yolov8n.pt")
print("YOLO model loaded successfully!")

# Find all MP4 videos
video_files = sorted(VIDEO_FOLDER.glob("*.mp4"))

if not video_files:
    print("No MP4 videos found in traffic_videos folder!")
    print("Please add MP4 files and try again.")
    raise SystemExit

print(f"\nFound {len(video_files)} videos:")

for video in video_files:
    print(" -", video.name)

print("\nStarting automatic video demonstration...")
print("Press Q to stop the demonstration.")

# Process videos one after another
for video_number, video_path in enumerate(video_files, start=1):

    print("\n======================================")
    print(f"Playing video {video_number}: {video_path.name}")
    print("======================================")

    cap = cv2.VideoCapture(str(video_path))

    if not cap.isOpened():
        print("Could not open:", video_path.name)
        continue

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0 or fps > 120:
        fps = 25

    frame_delay = max(1, int(1000 / fps))
    last_api_update = 0

    while True:
        success, frame = cap.read()

        if not success:
            print("Video completed:", video_path.name)
            break

        height, width = frame.shape[:2]
        mid_x = width // 2
        mid_y = height // 2

        # Resize frame for faster processing
        frame = cv2.resize(frame, (640, 360))

        height, width = frame.shape[:2]
        mid_x = width // 2
        mid_y = height // 2

        # Four road sections
        counts = {
            "Top Left": 0,
            "Top Right": 0,
            "Bottom Left": 0,
            "Bottom Right": 0
        }

        # Run YOLO detection
        results = model(
            frame,
            conf=0.35,
            classes=list(VEHICLE_CLASSES.keys()),
            verbose=False
        )

        for result in results:
            for box in result.boxes:

                class_id = int(box.cls[0])
                vehicle_name = VEHICLE_CLASSES.get(class_id, "Vehicle")
                confidence = float(box.conf[0])

                x1, y1, x2, y2 = map(
                    int, box.xyxy[0].tolist()
                )

                center_x = (x1 + x2) // 2
                center_y = (y1 + y2) // 2

                # Determine the quadrant
                if center_x < mid_x and center_y < mid_y:
                    road = "Top Left"
                elif center_x >= mid_x and center_y < mid_y:
                    road = "Top Right"
                elif center_x < mid_x and center_y >= mid_y:
                    road = "Bottom Left"
                else:
                    road = "Bottom Right"

                counts[road] += 1

                # Draw detection box
                label = f"{vehicle_name} {confidence:.2f}"

                cv2.rectangle(
                    frame,
                    (x1, y1),
                    (x2, y2),
                    (0, 255, 0),
                    2
                )

                cv2.putText(
                    frame,
                    label,
                    (x1, max(20, y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 255, 0),
                    2
                )

        # Draw quadrant lines
        cv2.line(
            frame, (mid_x, 0), (mid_x, height),
            (255, 255, 0), 2
        )

        cv2.line(
            frame, (0, mid_y), (width, mid_y),
            (255, 255, 0), 2
        )

        total = sum(counts.values())

        # Display video and counts
        cv2.putText(
            frame,
            f"CITINOVA AI | Video {video_number}",
            (10, 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 255),
            2
        )

        cv2.putText(
            frame,
            f"Total Vehicles: {total}",
            (10, 55),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 255),
            2
        )

        cv2.imshow("CITINOVA AI - Vehicle Detection", frame)

        # Send counts to Flask once every second
        current_time = time.time()

        if current_time - last_api_update >= 1:
            try:
                response = requests.post(
                    API_URL,
                    json=counts,
                    timeout=3
                )

                print(
                    f"Video {video_number} | "
                    f"Total: {total} | "
                    f"Dashboard: {response.status_code}"
                )

            except requests.RequestException as error:
                print("Backend connection error:", error)

            last_api_update = current_time

        # Press Q to stop
        key = cv2.waitKey(frame_delay) & 0xFF

        if key == ord("q"):
            print("Demonstration stopped by user.")
            cap.release()
            cv2.destroyAllWindows()
            raise SystemExit

    cap.release()

# All videos completed
cv2.destroyAllWindows()

print("\n======================================")
print("ALL VIDEOS COMPLETED!")
print("CITINOVA AI DEMONSTRATION FINISHED")
print("======================================")
