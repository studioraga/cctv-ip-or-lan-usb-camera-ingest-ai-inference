import cv2
import time

pipeline = (
    'udpsrc port=5000 caps="application/x-rtp,media=video,encoding-name=JPEG,payload=26" ! '
    'rtpjpegdepay ! jpegdec ! '
    'videoconvert ! video/x-raw,format=BGR ! '
    'appsink drop=true sync=false max-buffers=1'
)

cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)

if not cap.isOpened():
    raise RuntimeError("Failed to open Node2 MJPEG RTP stream")

frames = 0
t0 = time.time()

while True:
    ok, frame = cap.read()
    if not ok:
        print("Frame receive failed")
        break

    frames += 1

    # Node1 AI orchestration point:
    # 1. preprocess frame
    # 2. run object detection / visual agent / event logic
    # 3. send control command if needed

    if frames % 100 == 0:
        dt = time.time() - t0
        print(f"Received FPS: {frames / dt:.2f}, frame={frame.shape}")

    cv2.imshow("Node2 C922 stream on Node1", frame)
    if cv2.waitKey(1) == 27:
        break

cap.release()
cv2.destroyAllWindows()
